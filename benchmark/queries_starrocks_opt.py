"""
Queries sourced from Tim's and custom , filtered to the rows
tagged `tensoryze.processexecution_opt`. Copied as close to verbatim as
possible;
"""
def build_queries(sample_part_ids: list[str], target: str):

    is_starrocks = target == "starrocks"
    is_timescaledb = target == "timescaledb"

    # Identifier quoting
    q = "`" if is_starrocks else '"'

    ts = f"{q}timestamp{q}"

    # Portable IN (...) instead of PostgreSQL ANY(%s)
    placeholders = ", ".join(["%s"] * len(sample_part_ids))

    if is_starrocks:
        one_day_ago = f"""
            DATE_SUB(
                (SELECT MAX({ts})
                 FROM tensoryze.processexecution_time_opt),
                INTERVAL 1 DAY
            )
        """

        bucket_5min = f"""
            time_slice({ts}, INTERVAL 5 MINUTE)
        """

    else:
        one_day_ago = f"""
            (
                SELECT MAX({ts}) - INTERVAL '1 day'
                FROM tensoryze.processexecution_time_opt
            )
        """

        bucket_5min = f"""
            date_trunc('hour', {ts})
            + interval '5 min'
              * floor(extract(minute FROM {ts}) / 5)
        """

    queries = {

        "arrow_stream_smoke_test": (
            f"""
            SELECT *
            FROM tensoryze.processexecution_time_opt
            ORDER BY {ts} DESC
            LIMIT 100000
            """,
            None,
            "Arrow-stream smoke test",
        ),

        "timestamp_range_sanity": (
            f"""
            SELECT MIN({ts}) AS min_ts,
                   MAX({ts}) AS max_ts
            FROM tensoryze.processexecution_time_opt
            """,
            None,
            "UTC/timestamp-range sanity",
        ),

        "partquality_read": (
            """
            SELECT pe.*
            FROM tensoryze.processexecution_time_opt pe
            WHERE pe.id IN (
                SELECT part_id
                FROM tensoryze.partquality
            )
            """,
            None,
            "Read processexecution_time_opt rows matching partquality dataset",
        ),

        "per_part_read": (
            f"""
            SELECT
                pe.{ts},
                pe.id AS part_id,
                pe._field AS field_name,
                pe.namespace_id,
                COALESCE(
                    pe._value_str,
                    CAST(pe._value AS VARCHAR)
                ) AS value
            FROM tensoryze.processexecution_time_opt pe
            WHERE pe.id IN ({placeholders})
            ORDER BY pe.{ts} DESC
            """,
            tuple(sample_part_ids),
            "Partitioned per-part read for analysis dataset",
        ),

        "count_rows": (
            """
            SELECT COUNT(*)
            FROM tensoryze.processexecution_time_opt
            """,
            None,
            "Count all rows",
        ),

        "time_range_read": (
            f"""
            SELECT *
            FROM tensoryze.processexecution_time_opt
            WHERE {ts} >= {one_day_ago}
            ORDER BY {ts}
            """,
            None,
            "Read rows within a time range",
        ),

        "count_time_window": (
            f"""
            SELECT COUNT(*)
            FROM tensoryze.processexecution_time_opt
            WHERE {ts} >= {one_day_ago}
            """,
            None,
            "Count rows in a time window",
        ),

        "avg_5min": (
            f"""
            SELECT
                {bucket_5min} AS bucket,
                AVG(_value) AS avg_value
            FROM tensoryze.processexecution_time_opt
            GROUP BY bucket
            ORDER BY bucket
            """,
            None,
            "Average every 5 minutes",
        ),

        "min_max_5min": (
            f"""
            SELECT
                {bucket_5min} AS bucket,
                MIN(_value) AS min_value,
                MAX(_value) AS max_value
            FROM tensoryze.processexecution_time_opt
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
                {bucket_5min} AS bucket,
                COUNT(*) AS total
            FROM tensoryze.processexecution_time_opt
            GROUP BY namespace_id, bucket
            ORDER BY bucket
            """,
            None,
            "Count per namespace every 5 minutes",
        ),

        "distinct_parts_5min": (
            f"""
            SELECT
                {bucket_5min} AS bucket,
                COUNT(DISTINCT id) AS parts
            FROM tensoryze.processexecution_time_opt
            GROUP BY bucket
            ORDER BY bucket
            """,
            None,
            "Distinct parts every 5 minutes",
        ),

        "top_parts": (
            """
            SELECT
                id,
                COUNT(*) AS samples
            FROM tensoryze.processexecution_time_opt
            GROUP BY id
            ORDER BY samples DESC
            LIMIT 100
            """,
            None,
            "Top 100 parts by number of records",
        ),

        # Portable replacement for PostgreSQL DISTINCT ON
        "latest_per_part": (
            f"""
            SELECT
                id,
                {ts},
                _field,
                _value
            FROM (
                SELECT
                    id,
                    {ts},
                    _field,
                    _value,
                    ROW_NUMBER() OVER (
                        PARTITION BY id
                        ORDER BY {ts} DESC
                    ) AS rn
                FROM tensoryze.processexecution_time_opt
            ) t
            WHERE rn = 1
            """,
            None,
            "Latest record per part",
        ),
        
        "rolling_avg": (
            f"""
            SELECT
                id,
                {ts},
                AVG(_value) OVER (
                    PARTITION BY id
                    ORDER BY {ts}
                    ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
                ) AS rolling_avg
            FROM tensoryze.processexecution_time_opt
            """,
            None,
            "Rolling average (window function)",
        ),

        "lag_value": (
            f"""
            SELECT
                id,
                {ts},
                _value,
                LAG(_value) OVER (
                    PARTITION BY id
                    ORDER BY {ts}
                ) AS previous_value
            FROM tensoryze.processexecution_time_opt
            """,
            None,
            "Previous value using LAG",
        ),

        "row_number": (
            f"""
            SELECT
                id,
                {ts},
                ROW_NUMBER() OVER (
                    PARTITION BY id
                    ORDER BY {ts}
                ) AS rn
            FROM tensoryze.processexecution_time_opt
            """,
            None,
            "ROW_NUMBER window function",
        ),

        "join_avg_partquality": (
            """
            SELECT
                pq.part_id,
                AVG(pe._value) AS avg_value,
                COUNT(*) AS total
            FROM tensoryze.partquality pq
            JOIN tensoryze.processexecution_time_opt pe
                ON pe.id = pq.part_id
            GROUP BY pq.part_id
            """,
            None,
            "Join with partquality and aggregate",
        ),
    }

    # These are deliberately TimescaleDB-only.
    if is_timescaledb:

        queries["time_bucket_avg_5min"] = (
            f"""
            SELECT
                time_bucket('5 minutes', {ts}) AS bucket,
                AVG(_value) AS avg_value
            FROM tensoryze.processexecution_time_opt
            GROUP BY bucket
            ORDER BY bucket
            """,
            None,
            "TimescaleDB time_bucket aggregation",
        )

        queries["time_bucket_count_namespace"] = (
            f"""
            SELECT
                time_bucket('5 minutes', {ts}) AS bucket,
                namespace_id,
                COUNT(*) AS total
            FROM tensoryze.processexecution_time_opt
            GROUP BY bucket, namespace_id
            ORDER BY bucket
            """,
            None,
            "TimescaleDB namespace count per 5 minutes",
        )

    return queries
