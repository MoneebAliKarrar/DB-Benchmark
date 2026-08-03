from adapters.postgres_adapter import PostgresAdapter, PROCESSEXECUTION_INDEXES


class TimescaleDBAdapter(PostgresAdapter):
    """
    TimescaleDB speaks the Postgres wire protocol and SQL dialect, so this
    reuses PostgresAdapter entirely.

    One real constraint worth flagging: the production table's primary key
    is on `hash` alone, but TimescaleDB requires the partitioning column
    (`timestamp`) to be part of any unique constraint on a hypertable. So a
    disposable synthetic copy used to test TimescaleDB needs a composite PK
    (hash, timestamp) instead - this does NOT apply to the real production
    table, only to this benchmark's own generated copy (readonly=False runs).
    In readonly=True mode (pointed at an already-migrated real hypertable),
    this class does not touch the schema at all, same as PostgresAdapter.
    """
    name = "TimescaleDB"

    def _create_processexecution_table(self, cur):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tensoryze.processexecution (
                id              TEXT,
                hash            TEXT NOT NULL,
                "timestamp"     TIMESTAMP NOT NULL,
                time_key        TEXT,
                date_key        TEXT,
                namespace_id    TEXT,
                "_value"        REAL,
                "_field"        TEXT,
                "_value_str"    TEXT,
                created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                part_variant_id TEXT,
                CONSTRAINT processexecution_pkey PRIMARY KEY (hash, "timestamp")
            );
        """)
        for stmt in PROCESSEXECUTION_INDEXES:
            cur.execute(stmt)
        cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
        cur.execute(
            "SELECT create_hypertable('tensoryze.processexecution', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);"
        )

    def storage_size_mb(self) -> float:
        result, _ = self.run_query(
            "SELECT hypertable_size('tensoryze.processexecution');"
        )
        return result[0][0] / (1024 * 1024)