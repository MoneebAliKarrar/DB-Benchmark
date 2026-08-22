import time
import uuid

import pymysql

from adapters.base_adapter import BaseAdapter


class StarRocksAdapter(BaseAdapter):
    name = "StarRocks"

    def __init__(self, conn_config: dict, readonly: bool = True):
        self.config = conn_config
        self.conn = None
        self.readonly = readonly

    def connect(self):
        self.conn = pymysql.connect(
            host=self.config["host"],
            port=self.config.get("port", 9030),
            user=self.config.get("user", "root"),
            password=self.config.get("password", ""),
            database=self.config.get("database", "tensoryze"),
            autocommit=True,
            charset="utf8mb4",
        )

        with self.conn.cursor() as cur:
            cur.execute("SET query_timeout = 3600")

    def close(self):
        if self.conn:
            self.conn.close()

    def setup(self):
        """
        In readonly mode, only verify that the existing
        tensoryze.processexecution table exists.

        In generate mode, create the database/table if needed.
        """
        if self.readonly:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'tensoryze'
                      AND table_name = 'processexecution'
                """)
                exists = cur.fetchone()[0]

                if not exists:
                    raise RuntimeError(
                        "readonly=True but tensoryze.processexecution "
                        "does not exist in StarRocks."
                    )
            return

        with self.conn.cursor() as cur:
            cur.execute("CREATE DATABASE IF NOT EXISTS tensoryze")
            cur.execute("USE tensoryze")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS processexecution (
                    id              VARCHAR(255),
                    hash            VARCHAR(255) NOT NULL,
                    `timestamp`     DATETIME,
                    time_key        VARCHAR(255),
                    date_key        VARCHAR(255),
                    namespace_id    VARCHAR(255),
                    _value          FLOAT,
                    _field          VARCHAR(255),
                    _value_str      VARCHAR(255),
                    created_at      DATETIME NOT NULL,
                    updated_at      DATETIME NOT NULL,
                    part_variant_id VARCHAR(255)
                )
                DUPLICATE KEY(id, hash, `timestamp`)
                DISTRIBUTED BY HASH(id) BUCKETS 8
                PROPERTIES (
                    "replication_num" = "1"
                )
            """)

    def truncate(self):
        if self.readonly:
            raise RuntimeError(
                "Refusing to truncate StarRocks table: "
                "adapter is in readonly mode."
            )

        with self.conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE tensoryze.processexecution")

    def insert_batch(self, rows: list[tuple]):
        """
        Intended only for synthetic/generated benchmark mode.

        rows:
        (
            id,
            timestamp,
            time_key,
            date_key,
            namespace_id,
            value,
            field,
            value_str,
            part_variant_id
        )

        For the real 66M-row dataset, continue using Stream Load instead
        of this function.
        """

        now = None

        expanded = [
            (
                r[0],
                uuid.uuid4().hex,
                r[1],
                r[2],
                r[3],
                r[4],
                r[5],
                r[6],
                r[7],
                now,
                now,
                r[8],
            )
            for r in rows
        ]

        sql = """
            INSERT INTO tensoryze.processexecution (
                id,
                hash,
                `timestamp`,
                time_key,
                date_key,
                namespace_id,
                _value,
                _field,
                _value_str,
                created_at,
                updated_at,
                part_variant_id
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                %s
            )
        """

        insert_rows = [
            (
                r[0],
                r[1],
                r[2],
                r[3],
                r[4],
                r[5],
                r[6],
                r[7],
                r[8],
                r[11],
            )
            for r in expanded
        ]

        with self.conn.cursor() as cur:
            cur.executemany(sql, insert_rows)

    def insert_namespaces(self, rows: list[tuple]):
        """
        Not currently needed for the StarRocks readonly benchmark.
        Kept because BaseAdapter requires it.
        """
        raise NotImplementedError(
            "Namespace insertion is not implemented for StarRocks."
        )

    def run_query(self, sql_or_query, params=None):
        """
        Execute query and measure query + result retrieval time,
        consistent with the PostgreSQL adapter.
        """
        with self.conn.cursor() as cur:
            start = time.perf_counter()

            cur.execute(sql_or_query, params or ())
            result = cur.fetchall()

            elapsed = time.perf_counter() - start

        return result, elapsed

    def row_count(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM tensoryze.processexecution
            """)
            return cur.fetchone()[0]

    def storage_size_mb(self) -> float:
        """
        StarRocks exposes DATA_LENGTH in information_schema.tables.
        DATA_LENGTH is reported in bytes and represents the table's
        data size across replicas.
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT DATA_LENGTH
                FROM information_schema.tables
                WHERE TABLE_SCHEMA = 'tensoryze'
                  AND TABLE_NAME = 'processexecution'
            """)

            row = cur.fetchone()

            if not row or row[0] is None:
                raise RuntimeError(
                    "Could not determine StarRocks table size."
                )

            size_bytes = int(row[0])

            return round(size_bytes / (1024 * 1024), 2)