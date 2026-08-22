import argparse
import statistics
from datetime import datetime

import config
#from queries import build_queries
from queries_starrocks_opt import build_queries
from report import init_results_file, append_result

from adapters.postgres_adapter import PostgresAdapter
from adapters.timescaledb_adapter import TimescaleDBAdapter
from adapters.starrocks_adapter import StarRocksAdapter


ADAPTERS = {
    "postgres": lambda: PostgresAdapter(
        config.POSTGRES_CONFIG,
        readonly=True
    ),
    "timescaledb": lambda: TimescaleDBAdapter(
        config.TIMESCALEDB_CONFIG,
        readonly=True
    ),
    "starrocks": lambda readonly: StarRocksAdapter(
        config.STARROCKS_CONFIG,
        readonly=readonly
    ),
}


def get_sample_part_ids(adapter, n: int) -> list[str]:
    result, _ = adapter.run_query(
        "SELECT DISTINCT id FROM tensoryze.processexecution LIMIT %s;",
        (n,),
    )
    return [row[0] for row in result]


def run_queries_and_log(adapter, table_size_label, results_path: str):
    sample_part_ids = get_sample_part_ids(
        adapter,
        config.SAMPLE_PART_ID_COUNT,
    )

    if not sample_part_ids:
        print("WARNING: No part IDs found. Skipping per-part query.")

    queries = build_queries(sample_part_ids, adapter.name.lower())
    today = datetime.now().strftime("%Y-%m-%d")

    # Storage footprint
    size_mb = adapter.storage_size_mb()

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


def run_readonly(adapter, results_path: str):
    """
    Benchmark an existing table without modifying any data.
    """

    actual_rows = adapter.row_count()

    print(
        f"\n=== {adapter.name} (readonly): "
        f"existing table, {actual_rows:,} rows ==="
    )

    run_queries_and_log(
        adapter,
        actual_rows,
        results_path,
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

    args = parser.parse_args()

    adapter = ADAPTERS[args.target](readonly=True)

    results_path = init_results_file(
        config.RESULTS_DIR,
        args.target,
    )

    adapter.connect()

    try:
        adapter.setup()
        run_readonly(adapter, results_path)
    finally:
        adapter.close()

    print(f"\nDone. Results written to {results_path}")


if __name__ == "__main__":
    main()