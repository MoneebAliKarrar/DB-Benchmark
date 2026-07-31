import time
import uuid
import psycopg2
from psycopg2.extras import execute_values

from adapters.base_adapter import BaseAdapter

# Matches the real production table exactly (as provided via \d
PROCESSEXECUTION_DDL = """
    CREATE TABLE IF NOT EXISTS tensoryze.processexecution (
        id              TEXT,
        hash            TEXT NOT NULL,
        "timestamp"     TIMESTAMP,
        time_key        TEXT,
        date_key        TEXT,
        namespace_id    TEXT,
        "_value"        REAL,
        "_field"        TEXT,
        "_value_str"    TEXT,
        created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        part_variant_id TEXT,
        CONSTRAINT processexecution_pkey PRIMARY KEY (hash)
    );
"""
PROCESSEXECUTION_INDEXES = [
    'CREATE INDEX IF NOT EXISTS idx_processexecution_namespace ON tensoryze.processexecution (namespace_id);',
    'CREATE INDEX IF NOT EXISTS idx_processexecution_ts ON tensoryze.processexecution ("timestamp" DESC);',
]


class PostgresAdapter(BaseAdapter):
    name = "PostgreSQL"

    def __init__(self, conn_config: dict, readonly: bool = True):
        """
        readonly=True (default): setup()/truncate() never touch
        tensoryze.processexecution - use this whenever pointed at a table
        that already has real (or realistically restored) data, e.g. from
        backups/processexecution.dump. Only set readonly=False for a
        disposable synthetic-data run (a throwaway DB/schema).
        """
        self.config = conn_config
        self.conn = None
        self.readonly = readonly

    def connect(self):
        self.conn = psycopg2.connect(**self.config)
        self.conn.autocommit = True

    def close(self):
        if self.conn:
            self.conn.close()

    def setup(self):
        if self.readonly:
            # Real/restored environment: verify everything exists, but never
            # create, alter, or seed any of these three tables. namespace and
            # partquality are almost certainly real production tables too
            # (Tim's queries join/subquery against them), not just
            # processexecution, so treat all three the same way.
            with self.conn.cursor() as cur:
                for qualified_name in (
                    "tensoryze.processexecution",
                ):
                    cur.execute("SELECT to_regclass(%s);", (qualified_name,))
                    if cur.fetchone()[0] is None:
                        raise RuntimeError(
                            f"readonly=True but {qualified_name} does not exist. "
                            "Either this table needs to be loaded/restored first, or "
                            "pass readonly=False explicitly to generate synthetic data "
                            "into a disposable schema instead."
                        )
            return

        with self.conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS tensoryze;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tensoryze.namespace (
                    id    TEXT PRIMARY KEY,
                    label TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tensoryze.partquality (
                    part_id TEXT NOT NULL
                );
            """)
            self._create_processexecution_table(cur)
        self._seed_namespaces()

    def _create_processexecution_table(self, cur):
        """Overridden by TimescaleDBAdapter - the hash-only PK below matches
        the real production table exactly, but TimescaleDB hypertables
        require the partitioning column in any unique constraint, so a
        hypertable copy needs a composite PK instead."""
        cur.execute(PROCESSEXECUTION_DDL)
        for stmt in PROCESSEXECUTION_INDEXES:
            cur.execute(stmt)

    def truncate(self):
        if self.readonly:
            raise RuntimeError(
                "Refusing to truncate tensoryze.processexecution: adapter is in readonly "
                "mode (the default), meant to protect real/restored data. Pass "
                "readonly=False explicitly if you really intend to wipe and regenerate."
            )
        with self.conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE tensoryze.processexecution;")
            cur.execute("TRUNCATE TABLE tensoryze.partquality;")
            # namespace is intentionally NOT truncated - it's static reference data

    def insert_batch(self, rows: list[tuple]):
        """
        rows: (id, timestamp, time_key, date_key, namespace_id, value, field, value_str, part_variant_id)
        `hash` is generated here (uuid4) since it's the real PK and has no DB default.
        created_at/updated_at are left to their DB defaults.
        """
        expanded = [
            (r[0], uuid.uuid4().hex, r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8])
            for r in rows
        ]
        with self.conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO tensoryze.processexecution
                    (id, hash, "timestamp", time_key, date_key, namespace_id, "_value", "_field", "_value_str", part_variant_id)
                VALUES %s
                """,
                expanded,
                page_size=len(expanded),
            )

    def insert_namespaces(self, rows: list[tuple]):
        with self.conn.cursor() as cur:
            execute_values(cur, "INSERT INTO tensoryze.namespace (id, label) VALUES %s", rows)

    def run_query(self, sql_or_query, params=None):
        with self.conn.cursor() as cur:
            start = time.perf_counter()
            cur.execute(sql_or_query, params or ())
            result = cur.fetchall()
            elapsed = time.perf_counter() - start
        return result, elapsed

    def row_count(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tensoryze.processexecution;")
            return cur.fetchone()[0]

    def storage_size_mb(self) -> float:
        with self.conn.cursor() as cur:
            cur.execute("SELECT pg_total_relation_size('tensoryze.processexecution');")
            size_bytes = cur.fetchone()[0]
            return round(size_bytes / (1024 * 1024), 2)
