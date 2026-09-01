"""
Benchmark Postgres / TimescaleDB read performance via ConnectorX.

ConnectorX is tested separately from the psycopg2-based adapters because it
represents a different access pattern: a Python analytics client pulling a
full result set into a DataFrame (Pandas/Arrow), rather than a raw
server-side query. Timings here include connection setup, query execution,
data transfer, and DataFrame materialization - NOT directly comparable to
the EXPLAIN ANALYZE / psycopg2 latencies elsewhere in this project.

Two modes are benchmarked per query:
  - naive:       cx.read_sql(db_url, query)                — single connection
  - partitioned: cx.read_sql(..., partition_on=, partition_num=) — parallel reads

Only queries with no bind parameters (%s placeholders) can run through
ConnectorX as-is, since it takes a literal SQL string, not parameterized
SQL. per_part_read is skipped here for that reason (see NOTE below).
"""

import argparse
import statistics
import time
from datetime import datetime

import connectorx as cx

import config
from report import init_results_file, append_result


# --- Connection URLs -------------------------------------------------------
# ConnectorX requires the "postgresql://" scheme explicitly (not "postgres://").

def build_url(cfg: dict) -> str:
    return (
        f"postgresql://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
    )


DB_URLS = {
    "postgres": build_url(config.POSTGRES_CONFIG),
    "timescaledb": build_url(config.TIMESCALEDB_CONFIG),
}


# --- Queries ----------------------------------------------------------------
# Static (non-parameterized) versions of the queries from queries.py.
# per_part_read is intentionally excluded: it requires %s-style bind
# parameters (sample part IDs), which ConnectorX's read_sql does not accept -
# it only takes a plain SQL string. If you need that query benchmarked via
# ConnectorX, interpolate the IDs directly into the SQL string yourself
# (with care for SQL injection, since this is a controlled benchmark script
# only - never do this with user-supplied input).

CX_QUERIES = {
    "arrow_stream_smoke_test": (
        """
        SELECT * FROM tensoryze.processexecution
        ORDER BY "timestamp" DESC
        LIMIT 100000
        """,
        "Arrow-stream smoke test",
    ),
    "timestamp_range_sanity": (
        """
        SELECT MIN("timestamp") AS min_ts, MAX("timestamp") AS max_ts
        FROM tensoryze.processexecution
        """,
        "UTC/timestamp-range sanity",
    ),
    "partquality_read": (
        """
        SELECT pe.*
        FROM tensoryze.processexecution pe
        WHERE pe.id IN (
            SELECT part_id
            FROM tensoryze.partquality
        )
        """,
        "Read processexecution rows matching partquality dataset",
    ),
}

# Column used for ConnectorX's partitioned parallel read. "timestamp" is a
# natural fit here since it's the hypertable's partitioning dimension too.
PARTITION_COLUMN = "timestamp"
PARTITION_NUM = 8


# --- Core benchmark function --------------------------------------------

def benchmark_connectorx(
    db_url: str,
    query: str,
    partition_on: str = None,
    partition_num: int = None,
):
    start = time.perf_counter()

    if partition_on and partition_num:
        df = cx.read_sql(
            db_url,
            query,
            partition_on=partition_on,
            partition_num=partition_num,
        )
    else:
        df = cx.read_sql(db_url, query)

    elapsed = time.perf_counter() - start
    rows = len(df)

    return {
        "rows": rows,
        "seconds": elapsed,
        "rows_per_second": (rows / elapsed) if elapsed > 0 else None,
        "partitioned": bool(partition_on and partition_num),
    }


def run_repeated(db_url, query, partition_on=None, partition_num=None, repeats=5):
    """Run a query `repeats` times and return median/min/max latency in ms,
    plus the row count from the last run (should be constant across runs)."""
    timings_ms = []
    rows = None

    for _ in range(repeats):
        result = benchmark_connectorx(
            db_url, query,
            partition_on=partition_on,
            partition_num=partition_num,
        )
        timings_ms.append(result["seconds"] * 1000)
        rows = result["rows"]

    return {
        "median_ms": round(statistics.median(timings_ms), 2),
        "min_ms": round(min(timings_ms), 2),
        "max_ms": round(max(timings_ms), 2),
        "rows": rows,
    }


# --- Main runner, logging into the same CSV format as benchmark.py --------

def run_target(target: str, results_path: str):
    db_url = DB_URLS[target]
    technology_label = "PostgreSQL" if target == "postgres" else "TimescaleDB"
    today = datetime.now().strftime("%Y-%m-%d")

    print(f"\n=== ConnectorX benchmark: {technology_label} ===")

    for key, (sql, description) in CX_QUERIES.items():
        for mode, partition_on, partition_num in (
            ("naive", None, None),
            ("partitioned", PARTITION_COLUMN, PARTITION_NUM),
        ):
            label = f"{description} (ConnectorX, {mode})"
            try:
                stats = run_repeated(
                    db_url, sql,
                    partition_on=partition_on,
                    partition_num=partition_num,
                    repeats=config.QUERY_REPEATS,
                )
            except Exception as exc:
                print(f"  {label:<70} FAILED: {exc}")
                continue

            append_result(
                results_path,
                technology_label,
                None,  # table size label - filled in by caller if tracked elsewhere
                label,
                "Latency (median, ConnectorX end-to-end)",
                stats["median_ms"],
                "ms",
                config.VM_CONFIG_LABEL,
                today,
                (
                    f"min={stats['min_ms']}ms max={stats['max_ms']}ms "
                    f"n={config.QUERY_REPEATS} rows={stats['rows']} "
                    f"mode={mode}"
                ),
            )

            print(
                f"  {label:<70} "
                f"median={stats['median_ms']:>10} ms "
                f"(rows={stats['rows']})"
            )


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Postgres/TimescaleDB via ConnectorX."
    )
    parser.add_argument(
        "--target",
        default="postgres",
        choices=DB_URLS.keys(),
        help="Database to benchmark.",
    )
    args = parser.parse_args()

    results_path = init_results_file(config.RESULTS_DIR, f"{args.target}_connectorx")
    run_target(args.target, results_path)

    print(f"\nDone. Results written to {results_path}")


if __name__ == "__main__":
    main()