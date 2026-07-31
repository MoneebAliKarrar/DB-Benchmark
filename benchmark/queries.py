"""
Queries sourced from Tim's and custom , filtered to the rows
tagged `tensoryze.processexecution`. Copied as close to verbatim as
possible;
"""


def build_queries(sample_part_ids: list[str]):
    return {
        
        
        

        "arrow_stream_smoke_test": (
            """
            SELECT * FROM tensoryze.processexecution
            ORDER BY "timestamp" DESC
            LIMIT 100000
            """,
            None,
            "Arrow-stream smoke test",
        ),

        "timestamp_range_sanity": (
            """
            SELECT MIN("timestamp") AS min_ts, MAX("timestamp") AS max_ts
            FROM tensoryze.processexecution
            """,
            None,
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
            None,
            "Read processexecution rows matching partquality dataset",
        ),
        "per_part_read": (
            """
            SELECT pe."timestamp", pe.id AS part_id, pe."_field" AS field_name, pe.namespace_id,
                   COALESCE(pe."_value_str", CAST(pe."_value" AS VARCHAR)) AS value
            FROM tensoryze.processexecution pe
            WHERE pe.id = ANY(%s)
            ORDER BY pe."timestamp" DESC
            """,
            (list(sample_part_ids),),
            "Partitioned per-part read for analysis dataset",
        ),
    }
