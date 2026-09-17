import argparse
import statistics
from datetime import datetime

import config
from queries import build_queries
from report import init_results_file, append_result

from adapters.postgres_adapter import PostgresAdapter
from adapters.timescaledb_adapter import TimescaleDBAdapter
from adapters.starrocks_adapter import StarRocksAdapter
from adapters.clickhouse_adapter import ClickHouseAdapter


ADAPTERS = {

    "postgres": lambda readonly=False: PostgresAdapter(
        config.POSTGRES_CONFIG,
        readonly=readonly
    ),

    "timescaledb": lambda readonly=False: TimescaleDBAdapter(
        config.TIMESCALEDB_CONFIG,
        readonly=readonly
    ),

    "starrocks": lambda readonly=False: StarRocksAdapter(
        config.STARROCKS_CONFIG,
        readonly=readonly
    ),

    "clickhouse": lambda readonly=False: ClickHouseAdapter(
        config.CLICKHOUSE_CONFIG,
        readonly=readonly,
    ),

}


def get_sample_part_ids(
    adapter,
    n: int,
    table: str = "tensoryze.processexecution",
) -> list[str]:

    if adapter.dialect == "clickhouse":
        result, _ = adapter.run_query(
            f"""
            SELECT DISTINCT id
            FROM {table}
            LIMIT {n}
            """
        )
    else:
        result, _ = adapter.run_query(
            f"""
            SELECT DISTINCT id
            FROM {table}
            LIMIT %s
            """,
            (n,),
        )

    return [row[0] for row in result]


def run_queries_and_log(adapter, table_size_label, results_path: str ,target: str, table:str):
    sample_part_ids = get_sample_part_ids(
        adapter,
        config.SAMPLE_PART_ID_COUNT,
        table
    )

    if not sample_part_ids:
        print("WARNING: No part IDs found. Skipping per-part query.")

    queries = build_queries(
        sample_part_ids,
        target,
        table
    )
    today = datetime.now().strftime("%Y-%m-%d")

    # Storage footprint
    size_mb = adapter.storage_size_mb(table)

    append_result(
        results_path,
        adapter.name,
        table_size_label,
        "Storage footprint",
        "Size",
        size_mb,
        "MB",
        config.VM_CONFIG_LABEL,
        today,
        "",
    )

    print(f"Storage size: {size_mb} MB")

    # Benchmark each query
    for key, (sql, params, description) in queries.items():

        if key == "per_part_read" and not sample_part_ids:
            continue

        timings = []

        for _ in range(config.QUERY_REPEATS):
            _, elapsed = adapter.run_query(sql, params)
            timings.append(elapsed * 1000)  # milliseconds

        median_ms = round(statistics.median(timings), 2)
        min_ms = round(min(timings), 2)
        max_ms = round(max(timings), 2)

        append_result(
            results_path,
            adapter.name,
            table_size_label,
            description,
            "Latency (median)",
            median_ms,
            "ms",
            config.VM_CONFIG_LABEL,
            today,
            f"min={min_ms}ms max={max_ms}ms n={config.QUERY_REPEATS}",
        )

        print(
            f"  {description:<45} "
            f"median={median_ms:>9} ms "
            f"(min={min_ms}, max={max_ms})"
        )


def run_readonly(adapter, results_path: str,target, table: str):
    """
    Benchmark an existing table without modifying any data.
    """

    actual_rows = adapter.row_count(table)

    print(
        f"\n=== {adapter.name} (readonly): "
        f"existing table, {actual_rows:,} rows ==="
    )

    run_queries_and_log(
        adapter,
        actual_rows,
        results_path,
        target,
        table
    )


def main():
    parser = argparse.ArgumentParser(
        description="Run benchmark queries against an existing database."
    )

    parser.add_argument(
        "--target",
        default="postgres",
        choices=ADAPTERS.keys(),
        help="Database to benchmark.",
    )

    parser.add_argument(
        "--table",
        default="tensoryze.processexecution",
        help="processexecution table to benchmark.",
    )

    args = parser.parse_args()

    adapter = ADAPTERS[args.target](readonly=True)

    results_path = init_results_file(
        config.RESULTS_DIR,
        args.target,
    )

    adapter.connect()

    try:
        adapter.setup(args.table)
        run_readonly(adapter, results_path,args.target,args.table)
    finally:
        adapter.close()

    print(f"\nDone. Results written to {results_path}")


if __name__ == "__main__":
    main()