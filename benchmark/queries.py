"""
Common benchmark workload for:

- PostgreSQL
- TimescaleDB
- StarRocks
- ClickHouse

The goal is to keep the logical workload identical across all DBMSs.
Dialect-specific SQL is used only where syntax differs.

Database-specific feature benchmarks should NOT be added to this file.
"""

def build_queries(sample_part_ids: list[str], target: str):

    is_postgres = target == "postgres"
    is_timescaledb = target == "timescaledb"
    is_starrocks = target == "starrocks"
    is_clickhouse = target == "clickhouse"

    if target not in {
        "postgres",
        "timescaledb",
        "starrocks",
        "clickhouse",
    }:
        raise ValueError(f"Unsupported target: {target}")

    # ---------------------------------------------------------
    # Identifier quoting
    # ---------------------------------------------------------

    if is_starrocks or is_clickhouse:
        q = "`"
    else:
        q = '"'

    ts = f"{q}timestamp{q}"

    # ---------------------------------------------------------
    # Parameter syntax
    # ---------------------------------------------------------

    if is_clickhouse:
        # ClickHouse server-side Array(String) parameter
        part_filter = "pe.id IN {part_ids:Array(String)}"
        part_params = {
            "part_ids": sample_part_ids
        }

    else:
        placeholders = ", ".join(
            ["%s"] * len(sample_part_ids)
        )

        part_filter = f"pe.id IN ({placeholders})"
        part_params = tuple(sample_part_ids)

    # ---------------------------------------------------------
    # One-day interval
    # ---------------------------------------------------------

    if is_starrocks:

        one_day_ago = f"""
            DATE_SUB(
                (
                    SELECT MAX({ts})
                    FROM tensoryze.processexecution
                ),
                INTERVAL 1 DAY
            )
        """

    elif is_clickhouse:

        one_day_ago = f"""
            (
                SELECT MAX({ts}) - INTERVAL 1 DAY
                FROM tensoryze.processexecution
            )
        """

    else:

        one_day_ago = f"""
            (
                SELECT MAX({ts}) - INTERVAL '1 day'
                FROM tensoryze.processexecution
            )
        """

    # ---------------------------------------------------------
    # Five-minute bucket
    # ---------------------------------------------------------

    if is_starrocks:

        bucket_5min = f"""
            time_slice(
                {ts},
                INTERVAL 5 MINUTE
            )
        """

    elif is_clickhouse:

        bucket_5min = f"""
            toStartOfFiveMinutes({ts})
        """

    else:

        bucket_5min = f"""
            date_trunc('hour', {ts})
            + interval '5 min'
              * floor(
                    extract(minute FROM {ts}) / 5
                )
        """


    # ---------------------------------------------------------
    # Selectivity / filter-scaling windows
    # ---------------------------------------------------------
    # The logical time windows are identical across DBMSs.
    # Only interval syntax changes by dialect.

    if is_starrocks:
        ago_1_hour = f"""
            DATE_SUB(
                (SELECT MAX({ts}) FROM tensoryze.processexecution),
                INTERVAL 1 HOUR
            )
        """
        ago_6_hours = f"""
            DATE_SUB(
                (SELECT MAX({ts}) FROM tensoryze.processexecution),
                INTERVAL 6 HOUR
            )
        """
        ago_7_days = f"""
            DATE_SUB(
                (SELECT MAX({ts}) FROM tensoryze.processexecution),
                INTERVAL 7 DAY
            )
        """
        ago_30_days = f"""
            DATE_SUB(
                (SELECT MAX({ts}) FROM tensoryze.processexecution),
                INTERVAL 30 DAY
            )
        """

    elif is_clickhouse:
        ago_1_hour = f"""
            (
                SELECT MAX({ts}) - INTERVAL 1 HOUR
                FROM tensoryze.processexecution
            )
        """
        ago_6_hours = f"""
            (
                SELECT MAX({ts}) - INTERVAL 6 HOUR
                FROM tensoryze.processexecution
            )
        """
        ago_7_days = f"""
            (
                SELECT MAX({ts}) - INTERVAL 7 DAY
                FROM tensoryze.processexecution
            )
        """
        ago_30_days = f"""
            (
                SELECT MAX({ts}) - INTERVAL 30 DAY
                FROM tensoryze.processexecution
            )
        """

    else:
        ago_1_hour = f"""
            (
                SELECT MAX({ts}) - INTERVAL '1 hour'
                FROM tensoryze.processexecution
            )
        """
        ago_6_hours = f"""
            (
                SELECT MAX({ts}) - INTERVAL '6 hours'
                FROM tensoryze.processexecution
            )
        """
        ago_7_days = f"""
            (
                SELECT MAX({ts}) - INTERVAL '7 days'
                FROM tensoryze.processexecution
            )
        """
        ago_30_days = f"""
            (
                SELECT MAX({ts}) - INTERVAL '30 days'
                FROM tensoryze.processexecution
            )
        """


    # ---------------------------------------------------------
    # Queries
    # ---------------------------------------------------------

    queries = {
    # A. BASIC / SELECTIVE READS
        # =========================================================
    
        # 1. Count all rows
        "count_rows": (
            """
            SELECT COUNT(*)
            FROM tensoryze.processexecution
            """,
            None,
            "Count all rows",
        ),
    
        # 2. Timestamp range
        "timestamp_range_sanity": (
            f"""
            SELECT
                MIN({ts}) AS min_ts,
                MAX({ts}) AS max_ts
            FROM tensoryze.processexecution
            """,
            None,
            "UTC/timestamp-range sanity",
        ),
    
        # 3. Selective per-part read
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
            FROM tensoryze.processexecution pe
            WHERE {part_filter}
            ORDER BY pe.{ts} DESC
            """,
            part_params,
            "Partitioned per-part read for analysis dataset",
        ),
    
        # 4. Time-range raw read
        "time_range_read": (
            f"""
            SELECT *
            FROM tensoryze.processexecution
            WHERE {ts} >= {one_day_ago}
            ORDER BY {ts}
            """,
            None,
            "Read rows within a one-day time range",
        ),
    
        # 5. Count rows in time window
        "count_time_window": (
            f"""
            SELECT COUNT(*)
            FROM tensoryze.processexecution
            WHERE {ts} >= {one_day_ago}
            """,
            None,
            "Count rows in a one-day time window",
        ),
    
        # 6. Part-quality filtering
        "partquality_read": (
            """
            SELECT pe.*
            FROM tensoryze.processexecution pe
            WHERE pe.id IN (
                SELECT part_id
                FROM tensoryze.partquality
            )
            """,
            None,
            "Read processexecution rows matching partquality dataset",
        ),
    
        # 7. Application-facing extraction
        "arrow_stream_smoke_test": (
            f"""
            SELECT *
            FROM tensoryze.processexecution
            ORDER BY {ts} DESC
            LIMIT 100000
            """,
            None,
            "Arrow-stream smoke test",
        ),
    
    
        # =========================================================
    # B. AGGREGATION / GROUP BY
        # =========================================================
    
        # 8. Average every 5 minutes
        "avg_5min": (
            f"""
            SELECT
                {bucket_5min} AS bucket,
                AVG(_value) AS avg_value
            FROM tensoryze.processexecution
            GROUP BY bucket
            ORDER BY bucket
            """,
            None,
            "Average every 5 minutes",
        ),
    
        # 9. Min/max every 5 minutes
        "min_max_5min": (
            f"""
            SELECT
                {bucket_5min} AS bucket,
                MIN(_value) AS min_value,
                MAX(_value) AS max_value
            FROM tensoryze.processexecution
            GROUP BY bucket
            ORDER BY bucket
            """,
            None,
            "Min/Max every 5 minutes",
        ),
    
        # 10. Namespace count every 5 minutes
        "count_namespace_5min": (
            f"""
            SELECT
                namespace_id,
                {bucket_5min} AS bucket,
                COUNT(*) AS total
            FROM tensoryze.processexecution
            GROUP BY namespace_id, bucket
            ORDER BY bucket
            """,
            None,
            "Count per namespace every 5 minutes",
        ),
    
        # 11. Group by namespace
        "group_by_namespace": (
            """
            SELECT
                namespace_id,
                COUNT(*) AS total,
                AVG(_value) AS avg_value,
                MIN(_value) AS min_value,
                MAX(_value) AS max_value
            FROM tensoryze.processexecution
            GROUP BY namespace_id
            ORDER BY total DESC
            """,
            None,
            "Aggregate measurements per namespace",
        ),
    
        # 12. Group by field
        "group_by_field": (
            """
            SELECT
                _field,
                COUNT(*) AS total,
                AVG(_value) AS avg_value,
                MIN(_value) AS min_value,
                MAX(_value) AS max_value
            FROM tensoryze.processexecution
            GROUP BY _field
            ORDER BY total DESC
            """,
            None,
            "Aggregate measurements per field",
        ),
    
        # 13. Group by namespace + field
        "group_by_namespace_field": (
            """
            SELECT
                namespace_id,
                _field,
                COUNT(*) AS total,
                AVG(_value) AS avg_value
            FROM tensoryze.processexecution
            GROUP BY namespace_id, _field
            ORDER BY total DESC
            """,
            None,
            "Group by namespace and field",
        ),
    
        # 14. Group by part
        "group_by_part": (
            """
            SELECT
                id,
                COUNT(*) AS total,
                AVG(_value) AS avg_value,
                MIN(_value) AS min_value,
                MAX(_value) AS max_value
            FROM tensoryze.processexecution
            GROUP BY id
            ORDER BY total DESC
            """,
            None,
            "Aggregate all measurements per part",
        ),
    
        # 15. Time + namespace + field grouping
        "group_time_namespace_field": (
            f"""
            SELECT
                {bucket_5min} AS bucket,
                namespace_id,
                _field,
                COUNT(*) AS total,
                AVG(_value) AS avg_value
            FROM tensoryze.processexecution
            GROUP BY bucket, namespace_id, _field
            ORDER BY bucket, namespace_id, _field
            """,
            None,
            "Multi-dimensional 5-minute aggregation",
        ),
    
        # 16. Time + part grouping
        "group_time_part": (
            f"""
            SELECT
                {bucket_5min} AS bucket,
                id,
                COUNT(*) AS total,
                AVG(_value) AS avg_value
            FROM tensoryze.processexecution
            GROUP BY bucket, id
            ORDER BY bucket, id
            """,
            None,
            "5-minute aggregation per part",
        ),
    
        # 17. GROUP BY + HAVING
        "group_having_large_parts": (
            """
            SELECT
                id,
                COUNT(*) AS total,
                AVG(_value) AS avg_value
            FROM tensoryze.processexecution
            GROUP BY id
            HAVING COUNT(*) > 1000
            ORDER BY total DESC
            """,
            None,
            "Group parts and filter aggregated groups",
        ),
    
        # 18. Nested/two-stage aggregation
        "nested_grouping": (
            """
            SELECT
                namespace_id,
                AVG(part_avg) AS avg_of_part_averages,
                MAX(part_avg) AS max_part_average
            FROM (
                SELECT
                    namespace_id,
                    id,
                    AVG(_value) AS part_avg
                FROM tensoryze.processexecution
                GROUP BY namespace_id, id
            ) t
            GROUP BY namespace_id
            ORDER BY avg_of_part_averages DESC
            """,
            None,
            "Two-stage aggregation",
        ),
    
    
        # =========================================================
    # C. SORTING / DISTINCT
        # =========================================================
    
        # 19. Top 100 parts
        "top_parts": (
            """
            SELECT
                id,
                COUNT(*) AS samples
            FROM tensoryze.processexecution
            GROUP BY id
            ORDER BY samples DESC
            LIMIT 100
            """,
            None,
            "Top 100 parts by number of records",
        ),
    
        # 20. Large timestamp sort
        "order_by_timestamp_desc": (
            f"""
            SELECT
                id,
                {ts},
                namespace_id,
                _field,
                _value
            FROM tensoryze.processexecution
            ORDER BY {ts} DESC
            LIMIT 1000000
            """,
            None,
            "Sort and return latest 1M rows",
        ),
    
        # 21. Multi-column sort
        "order_by_part_timestamp": (
            f"""
            SELECT
                id,
                {ts},
                _field,
                _value
            FROM tensoryze.processexecution
            ORDER BY id, {ts} DESC
            LIMIT 1000000
            """,
            None,
            "Sort 1M rows by part and timestamp",
        ),
    
        # 22. Numeric-value sort
        "order_by_value_desc": (
            f"""
            SELECT
                id,
                {ts},
                namespace_id,
                _value
            FROM tensoryze.processexecution
            WHERE _value IS NOT NULL
            ORDER BY _value DESC
            LIMIT 100000
            """,
            None,
            "Sort numeric measurements by value",
        ),
    
        # 23. Exact distinct parts per 5 minutes
        "distinct_parts_5min": (
            f"""
            SELECT
                {bucket_5min} AS bucket,
                COUNT(DISTINCT id) AS parts
            FROM tensoryze.processexecution
            GROUP BY bucket
            ORDER BY bucket
            """,
            None,
            "Distinct parts every 5 minutes",
        ),
    
        # 24. Distinct namespace-field combinations
        "distinct_namespace_field": (
            """
            SELECT DISTINCT
                namespace_id,
                _field
            FROM tensoryze.processexecution
            ORDER BY namespace_id, _field
            """,
            None,
            "Distinct namespace-field combinations",
        ),
    
        # 25. Distinct fields per namespace
        "distinct_fields_per_namespace": (
            """
            SELECT
                namespace_id,
                COUNT(DISTINCT _field) AS distinct_fields
            FROM tensoryze.processexecution
            GROUP BY namespace_id
            ORDER BY distinct_fields DESC
            """,
            None,
            "Distinct field count per namespace",
        ),
    
        # 26. GROUP BY + multi-column ORDER BY
        "group_order_multiple_columns": (
            """
            SELECT
                namespace_id,
                _field,
                COUNT(*) AS total,
                AVG(_value) AS avg_value
            FROM tensoryze.processexecution
            GROUP BY namespace_id, _field
            ORDER BY
                namespace_id ASC,
                total DESC,
                avg_value DESC
            """,
            None,
            "Grouped results ordered by multiple keys",
        ),
    
    
        # =========================================================
    # D. ANALYTICAL / WINDOW FUNCTIONS
        # =========================================================
    
        # 27. Latest record per part
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
                FROM tensoryze.processexecution
            ) t
            WHERE rn = 1
            """,
            None,
            "Latest record per part",
        ),
    
        # 28. Latest 10 records per part
        "latest_10_per_part": (
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
                FROM tensoryze.processexecution
            ) t
            WHERE rn <= 10
            """,
            None,
            "Latest 10 measurements per part",
        ),
    
        # 29. Rolling average
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
            FROM tensoryze.processexecution
            """,
            None,
            "10-row rolling average",
        ),
    
        # 30. LAG
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
            FROM tensoryze.processexecution
            """,
            None,
            "Previous value using LAG",
        ),
    
        # 31. ROW_NUMBER
        "row_number": (
            f"""
            SELECT
                id,
                {ts},
                ROW_NUMBER() OVER (
                    PARTITION BY id
                    ORDER BY {ts}
                ) AS rn
            FROM tensoryze.processexecution
            """,
            None,
            "ROW_NUMBER window function",
        ),
    
        # 32. Ranking aggregated parts
        "rank_parts_by_count": (
            """
            SELECT
                id,
                total,
                RANK() OVER (
                    ORDER BY total DESC
                ) AS rank_position
            FROM (
                SELECT
                    id,
                    COUNT(*) AS total
                FROM tensoryze.processexecution
                GROUP BY id
            ) t
            """,
            None,
            "Rank parts by number of samples",
        ),
    
        # 33. Ranking values inside each part
        "rank_values_per_part": (
            f"""
            SELECT
                id,
                {ts},
                _value,
                ROW_NUMBER() OVER (
                    PARTITION BY id
                    ORDER BY _value DESC
                ) AS value_rank
            FROM tensoryze.processexecution
            WHERE _value IS NOT NULL
            """,
            None,
            "Rank measurements within each part",
        ),
    
    
        # =========================================================
    # E. JOIN / RELATIONAL
        # =========================================================
    
        # 34. Join + aggregation
        "join_avg_partquality": (
            """
            SELECT
                pq.part_id,
                AVG(pe._value) AS avg_value,
                COUNT(*) AS total
            FROM tensoryze.partquality pq
            JOIN tensoryze.processexecution pe
                ON pe.id = pq.part_id
            GROUP BY pq.part_id
            """,
            None,
            "Join with partquality and aggregate",
        ),
        # =========================================================
        # 35. Inner join without aggregation
        "join_raw_partquality": (
            f"""
            SELECT
                pq.part_id,
                pe.{ts},
                pe._field,
                pe._value
            FROM tensoryze.partquality pq
            JOIN tensoryze.processexecution pe
                ON pe.id = pq.part_id
            LIMIT 1000000
            """,
            None,
            "Raw inner join between partquality and processexecution",
        ),
    
        # 36. Join + time filter
        "join_time_filtered": (
            f"""
            SELECT
                pq.part_id,
                COUNT(*) AS total,
                AVG(pe._value) AS avg_value
            FROM tensoryze.partquality pq
            JOIN tensoryze.processexecution pe
                ON pe.id = pq.part_id
            WHERE pe.{ts} >= {one_day_ago}
            GROUP BY pq.part_id
            ORDER BY total DESC
            """,
            None,
            "Join, time filter and aggregate",
        ),
    
        # 37. Join + GROUP BY multiple dimensions
        "join_group_field": (
            """
            SELECT
                pq.part_id,
                pe._field,
                COUNT(*) AS total,
                AVG(pe._value) AS avg_value
            FROM tensoryze.partquality pq
            JOIN tensoryze.processexecution pe
                ON pe.id = pq.part_id
            GROUP BY
                pq.part_id,
                pe._field
            ORDER BY total DESC
            """,
            None,
            "Join with multi-dimensional aggregation",
        ),
    
        # 38. EXISTS subquery
        "exists_partquality": (
            """
            SELECT COUNT(*)
            FROM tensoryze.processexecution pe
            WHERE EXISTS (
                SELECT 1
                FROM tensoryze.partquality pq
                WHERE pq.part_id = pe.id
            )
            """,
            None,
            "Correlated EXISTS lookup against partquality",
        ),
    
        # =========================================================
    # F. FILTERING / PREDICATES
        # =========================================================
    
        # 39. Numeric filter
        "filter_numeric_value": (
            f"""
            SELECT
                id,
                {ts},
                namespace_id,
                _field,
                _value
            FROM tensoryze.processexecution
            WHERE _value > 0
            """,
            None,
            "Filter rows using a numeric predicate",
        ),
    
        # 40. NULL filtering
        "filter_not_null": (
            """
            SELECT COUNT(*)
            FROM tensoryze.processexecution
            WHERE _value IS NOT NULL
            """,
            None,
            "Count non-null numeric measurements",
        ),
    
        # 41. Multiple predicates
        "filter_multiple_conditions": (
            f"""
            SELECT
                id,
                {ts},
                namespace_id,
                _field,
                _value
            FROM tensoryze.processexecution
            WHERE
                {ts} >= {one_day_ago}
                AND _value IS NOT NULL
                AND namespace_id IS NOT NULL
            """,
            None,
            "Combined timestamp, null and namespace filtering",
        ),
    
        # 42. Filter + ORDER BY
        "filter_order_timestamp": (
            f"""
            SELECT
                id,
                {ts},
                namespace_id,
                _value
            FROM tensoryze.processexecution
            WHERE _value IS NOT NULL
            ORDER BY {ts} DESC
            LIMIT 500000
            """,
            None,
            "Filter measurements then sort by timestamp",
        ),
    
        # 43. Filter + value ORDER BY
        "filter_order_value": (
            f"""
            SELECT
                id,
                {ts},
                _value
            FROM tensoryze.processexecution
            WHERE
                {ts} >= {one_day_ago}
                AND _value IS NOT NULL
            ORDER BY _value DESC
            LIMIT 100000
            """,
            None,
            "Time filter followed by numeric sorting",
        ),
    
        # 44. String-field filter
        "filter_field_not_null": (
            """
            SELECT
                _field,
                COUNT(*) AS total
            FROM tensoryze.processexecution
            WHERE _field IS NOT NULL
            GROUP BY _field
            ORDER BY total DESC
            """,
            None,
            "Filter and aggregate textual field values",
        ),
    
    
        # =========================================================
    # G. COMPLEX ANALYTICAL QUERIES
        # =========================================================
    
        # 45. Aggregation + ranking
        "rank_namespaces": (
            """
            SELECT
                namespace_id,
                total,
                avg_value,
                RANK() OVER (
                    ORDER BY total DESC
                ) AS namespace_rank
            FROM (
                SELECT
                    namespace_id,
                    COUNT(*) AS total,
                    AVG(_value) AS avg_value
                FROM tensoryze.processexecution
                GROUP BY namespace_id
            ) t
            """,
            None,
            "Aggregate namespaces and rank them",
        ),
    
        # 46. Aggregation + window over aggregated values
        "running_count_by_bucket": (
            f"""
            SELECT
                bucket,
                total,
                SUM(total) OVER (
                    ORDER BY bucket
                    ROWS BETWEEN UNBOUNDED PRECEDING
                    AND CURRENT ROW
                ) AS cumulative_total
            FROM (
                SELECT
                    {bucket_5min} AS bucket,
                    COUNT(*) AS total
                FROM tensoryze.processexecution
                GROUP BY bucket
            ) t
            ORDER BY bucket
            """,
            None,
            "Cumulative count over time buckets",
        ),
    
        # 47. Difference between consecutive measurements
        "value_difference": (
            f"""
            SELECT
                id,
                {ts},
                _value,
                _value - LAG(_value) OVER (
                    PARTITION BY id
                    ORDER BY {ts}
                ) AS value_difference
            FROM tensoryze.processexecution
            WHERE _value IS NOT NULL
            """,
            None,
            "Difference between consecutive numeric measurements",
        ),
    
        # 48. Running average per part
        "cumulative_avg_per_part": (
            f"""
            SELECT
                id,
                {ts},
                AVG(_value) OVER (
                    PARTITION BY id
                    ORDER BY {ts}
                    ROWS BETWEEN UNBOUNDED PRECEDING
                    AND CURRENT ROW
                ) AS cumulative_avg
            FROM tensoryze.processexecution
            """,
            None,
            "Cumulative average for each part",
        ),
    
        # 49. Running count per part
        "cumulative_count_per_part": (
            f"""
            SELECT
                id,
                {ts},
                COUNT(*) OVER (
                    PARTITION BY id
                    ORDER BY {ts}
                    ROWS BETWEEN UNBOUNDED PRECEDING
                    AND CURRENT ROW
                ) AS cumulative_count
            FROM tensoryze.processexecution
            """,
            None,
            "Cumulative record count per part",
        ),
    
        # 50. Nested aggregation + top-N
        "top_parts_by_avg_value": (
            """
            SELECT
                id,
                AVG(_value) AS avg_value,
                COUNT(*) AS total
            FROM tensoryze.processexecution
            WHERE _value IS NOT NULL
            GROUP BY id
            HAVING COUNT(*) > 100
            ORDER BY avg_value DESC
            LIMIT 100
            """,
            None,
            "Top parts by average numeric value",
        ),
    
        # 51. Bucket + namespace + HAVING
        "bucket_namespace_having": (
            f"""
            SELECT
                {bucket_5min} AS bucket,
                namespace_id,
                COUNT(*) AS total,
                AVG(_value) AS avg_value
            FROM tensoryze.processexecution
            GROUP BY
                bucket,
                namespace_id
            HAVING COUNT(*) > 100
            ORDER BY
                bucket,
                total DESC
            """,
            None,
            "Time and namespace aggregation with HAVING",
        ),
    
        # 52. Latest timestamp per namespace
        "latest_per_namespace": (
            f"""
            SELECT
                namespace_id,
                MAX({ts}) AS latest_timestamp,
                COUNT(*) AS total
            FROM tensoryze.processexecution
            GROUP BY namespace_id
            ORDER BY latest_timestamp DESC
            """,
            None,
            "Latest timestamp and count per namespace",
        ),
    
        # =========================================================
        # H. SELECTIVITY / FILTER SCALING
        # =========================================================
        #
        # Same COUNT(*) operation with progressively wider timestamp
        # windows. This isolates predicate/selectivity behavior while
        # keeping result transfer tiny and comparable.
    
        # 53. Selectivity: last 1 hour
        "selectivity_1_hour": (
            f"""
            SELECT COUNT(*)
            FROM tensoryze.processexecution
            WHERE {ts} >= {ago_1_hour}
            """,
            None,
            "Count rows in the latest 1-hour window",
        ),
    
        # 54. Selectivity: last 6 hours
        "selectivity_6_hours": (
            f"""
            SELECT COUNT(*)
            FROM tensoryze.processexecution
            WHERE {ts} >= {ago_6_hours}
            """,
            None,
            "Count rows in the latest 6-hour window",
        ),
    
        # 55. Selectivity: last 1 day
        "selectivity_1_day": (
            f"""
            SELECT COUNT(*)
            FROM tensoryze.processexecution
            WHERE {ts} >= {one_day_ago}
            """,
            None,
            "Count rows in the latest 1-day window",
        ),
    
        # 56. Selectivity: last 7 days
        "selectivity_7_days": (
            f"""
            SELECT COUNT(*)
            FROM tensoryze.processexecution
            WHERE {ts} >= {ago_7_days}
            """,
            None,
            "Count rows in the latest 7-day window",
        ),
    
        # 57. Selectivity: last 30 days
        "selectivity_30_days": (
            f"""
            SELECT COUNT(*)
            FROM tensoryze.processexecution
            WHERE {ts} >= {ago_30_days}
            """,
            None,
            "Count rows in the latest 30-day window",
        ),
    }

    return queries