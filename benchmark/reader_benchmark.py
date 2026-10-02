import argparse
import statistics
import time

import config
from adapters.clickhouse_adapter import ClickHouseAdapter
from queries import build_queries


SELECTED_QUERIES = [
    "count_rows",
    "time_range_read",
    "avg_5min",
    "group_by_part",
    "order_by_timestamp_desc",
    "rank_parts_by_count",
    "join_avg_partquality",
    "filter_multiple_conditions",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--table",
        default="tensoryze.processexecution_table_opt",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
    )
    args = parser.parse_args()

    adapter = ClickHouseAdapter(
        config.CLICKHOUSE_CONFIG,
        readonly=True,
    )

    adapter.connect()

    try:
        # Same idea used by the normal benchmark:
        # obtain sample IDs for build_queries().
        result, _ = adapter.run_query(
            f"""
            SELECT DISTINCT id
            FROM {args.table}
            LIMIT 3
            """
        )

        sample_ids = [row[0] for row in result]

        queries = build_queries(
            sample_ids,
            "clickhouse",
            args.table,
        )

        print(
            f"Host: {config.CLICKHOUSE_CONFIG['host']} "
            f"Table: {args.table}"
        )

        workload_start = time.perf_counter()
        successful = 0

        for key in SELECTED_QUERIES:
            sql, params, description = queries[key]

            timings = []

            for _ in range(args.repeats):
                _, elapsed = adapter.run_query(sql, params)
                timings.append(elapsed * 1000)

            median_ms = statistics.median(timings)

            print(
                f"{key:<30} "
                f"median={median_ms:.2f} ms"
            )

            successful += 1

        total_seconds = time.perf_counter() - workload_start

        print()
        print(f"Queries: {successful}")
        print(f"Repeats: {args.repeats}")
        print(f"Executions: {successful * args.repeats}")
        print(f"TOTAL_SECONDS={total_seconds:.3f}")

    finally:
        adapter.close()


if __name__ == "__main__":
    main()