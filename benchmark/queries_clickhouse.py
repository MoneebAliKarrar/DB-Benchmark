"""
ClickHouse benchmark queries.

Contains:
1. The same logical workload used for PostgreSQL / TimescaleDB / StarRocks.
2. A small ClickHouse-native section to test functions ClickHouse is
   specifically optimized for.

Target table:
    tensoryze.processexecution
"""

def build_queries(sample_part_ids: list[str], target: str = "clickhouse"):

    table = "tensoryze.processexecution"

    # ClickHouse Connect server-side parameter syntax.
    #
    # Query:
    #     WHERE id IN {part_ids:Array(String)}
    #
    # Params:
    #     {"part_ids": ["a", "b", ...]}
    part_params = {
        "part_ids": list(sample_part_ids)
    }

    queries = {

        # --------------------------------------------------
        # Common workload
        # --------------------------------------------------

        "arrow_stream_smoke_test": (
            f"""
            SELECT *
            FROM {table}
            ORDER BY `timestamp` DESC
            LIMIT 100000
            """,
            None,
            "Arrow-stream smoke test",
        ),

        "timestamp_range_sanity": (
            f"""
            SELECT
                min(`timestamp`) AS min_ts,
                max(`timestamp`) AS max_ts
            FROM {table}
            """,
            None,
            "UTC/timestamp-range sanity",
        ),

        "partquality_local_dist_read": (
            f"""
            SELECT pe.*
            FROM {table} AS pe
            WHERE pe.id IN (
                SELECT part_id
                FROM tensoryze.partquality_local_dist
            )
            """,
            None,
            "Read processexecution rows matching partquality_local_dist dataset",
        ),

        "per_part_read": (
            f"""
            SELECT
                pe.`timestamp`,
                pe.id AS part_id,
                pe._field AS field_name,
                pe.namespace_id,
                coalesce(
                    nullIf(pe._value_str, ''),
                    toString(pe._value)
                ) AS value
            FROM {table} AS pe
            WHERE pe.id IN {{part_ids:Array(String)}}
            ORDER BY pe.`timestamp` DESC
            """,
            part_params,
            "Partitioned per-part read for analysis dataset",
        ),

        "count_rows": (
            f"""
            SELECT count()
            FROM {table}
            """,
            None,
            "Count all rows",
        ),

        "time_range_read": (
            f"""
            SELECT *
            FROM {table}
            WHERE `timestamp` >= (
                SELECT max(`timestamp`) - INTERVAL 1 DAY
                FROM {table}
            )
            ORDER BY `timestamp`
            """,
            None,
            "Read rows within a time range",
        ),

        "count_time_window": (
            f"""
            SELECT count()
            FROM {table}
            WHERE `timestamp` >= (
                SELECT max(`timestamp`) - INTERVAL 1 DAY
                FROM {table}
            )
            """,
            None,
            "Count rows in a time window",
        ),

        "avg_5min": (
            f"""
            SELECT
                toStartOfFiveMinutes(`timestamp`) AS bucket,
                avg(_value) AS avg_value
            FROM {table}
            GROUP BY bucket
            ORDER BY bucket
            """,
            None,
            "Average every 5 minutes",
        ),

        "min_max_5min": (
            f"""
            SELECT
                toStartOfFiveMinutes(`timestamp`) AS bucket,
                min(_value) AS min_value,
                max(_value) AS max_value
            FROM {table}
            GROUP BY bucket
            ORDER BY bucket
            """,
            None,
            "Min/Max every 5 minutes",
        ),

        "count_namespace_5min": (
            f"""
            SELECT
                namespace_id,
                toStartOfFiveMinutes(`timestamp`) AS bucket,
                count() AS total
            FROM {table}
            GROUP BY
                namespace_id,
                bucket
            ORDER BY bucket
            """,
            None,
            "Count per namespace every 5 minutes",
        ),

        "distinct_parts_5min": (
            f"""
            SELECT
                toStartOfFiveMinutes(`timestamp`) AS bucket,
                uniqExact(id) AS parts
            FROM {table}
            GROUP BY bucket
            ORDER BY bucket
            """,
            None,
            "Distinct parts every 5 minutes",
        ),

        "top_parts": (
            f"""
            SELECT
                id,
                count() AS samples
            FROM {table}
            GROUP BY id
            ORDER BY samples DESC
            LIMIT 100
            """,
            None,
            "Top 100 parts by number of records",
        ),

        # Keep the generic ROW_NUMBER approach so this query remains
        # logically comparable with the other databases.
        "latest_per_part": (
            f"""
            SELECT
                id,
                `timestamp`,
                _field,
                _value
            FROM
            (
                SELECT
                    id,
                    `timestamp`,
                    _field,
                    _value,
                    row_number() OVER (
                        PARTITION BY id
                        ORDER BY `timestamp` DESC
                    ) AS rn
                FROM {table}
            )
            WHERE rn = 1
            """,
            None,
            "Latest record per part",
        ),

        "rolling_avg": (
            f"""
            SELECT
                id,
                `timestamp`,
                avg(_value) OVER (
                    PARTITION BY id
                    ORDER BY `timestamp`
                    ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
                ) AS rolling_avg
            FROM {table}
            """,
            None,
            "Rolling average (window function)",
        ),

        "lag_value": (
            f"""
            SELECT
                id,
                `timestamp`,
                _value,
                lag(_value, 1) OVER (
                    PARTITION BY id
                    ORDER BY `timestamp`
                ) AS previous_value
            FROM {table}
            """,
            None,
            "Previous value using LAG",
        ),

        "row_number": (
            f"""
            SELECT
                id,
                `timestamp`,
                row_number() OVER (
                    PARTITION BY id
                    ORDER BY `timestamp`
                ) AS rn
            FROM {table}
            """,
            None,
            "ROW_NUMBER window function",
        ),

        "join_avg_partquality_local_dist": (
            f"""
            SELECT
                pq.part_id,
                avg(pe._value) AS avg_value,
                count() AS total
            FROM tensoryze.partquality_local_dist AS pq
            INNER JOIN {table} AS pe
                ON pe.id = pq.part_id
            GROUP BY pq.part_id
            """,
            None,
            "Join with partquality_local_dist and aggregate",
        ),

        # --------------------------------------------------
        # ClickHouse-native workload
        # --------------------------------------------------

        "clickhouse_argmax_latest_per_part": (
            f"""
            SELECT
                id,
                argMax(`timestamp`, `timestamp`) AS latest_timestamp,
                argMax(_field, `timestamp`) AS latest_field,
                argMax(_value, `timestamp`) AS latest_value
            FROM {table}
            GROUP BY id
            """,
            None,
            "ClickHouse argMax latest record per part",
        ),

        "clickhouse_approx_distinct_parts_5min": (
            f"""
            SELECT
                toStartOfFiveMinutes(`timestamp`) AS bucket,
                uniq(id) AS parts
            FROM {table}
            GROUP BY bucket
            ORDER BY bucket
            """,
            None,
            "ClickHouse approximate distinct parts every 5 minutes",
        ),

        "clickhouse_quantiles_5min": (
            f"""
            SELECT
                toStartOfFiveMinutes(`timestamp`) AS bucket,
                quantiles(0.50, 0.95, 0.99)(_value) AS percentiles
            FROM {table}
            GROUP BY bucket
            ORDER BY bucket
            """,
            None,
            "ClickHouse value percentiles every 5 minutes",
        ),

        "clickhouse_topk_parts": (
            f"""
            SELECT topK(100)(id)
            FROM {table}
            """,
            None,
            "ClickHouse topK parts",
        ),
    }

    return queries