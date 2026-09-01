import time
import uuid
from datetime import datetime, timezone

import clickhouse_connect

from adapters.base_adapter import BaseAdapter


class ClickHouseAdapter(BaseAdapter):
    name = "ClickHouse"
    dialect = "clickhouse"

    def __init__(self, conn_config: dict, readonly: bool = True):
        """
        readonly=True:
            Use an already-populated ClickHouse table and never modify it.

        readonly=False:
            Allow setup(), truncate(), insert_batch(), etc. for
            disposable synthetic-data benchmarks.
        """
        self.config = conn_config
        self.client = None
        self.readonly = readonly

    # --------------------------------------------------
    # Connection
    # --------------------------------------------------

    def connect(self):
        """
        clickhouse-connect uses ClickHouse's HTTP interface.

        When running from the benchmark Docker container,
        host should be the ClickHouse Docker DNS/container name,
        e.g. tsdb_clickhouse, and port should normally be 8123.
        """
        self.client = clickhouse_connect.get_client(
            host=self.config.get("host", "tsdb_clickhouse"),
            port=self.config.get("port", 8123),
            username=self.config.get("user", "admin"),
            password=self.config.get("password", "admin"),
            database=self.config.get("database", "tensoryze"),
        )

        # Simple connection sanity check.
        self.client.command("SELECT 1")

    def close(self):
        if self.client is not None:
            self.client.close()
            self.client = None

    # --------------------------------------------------
    # Setup
    # --------------------------------------------------

    def setup(self):
        """
        readonly=True:
            Verify the benchmark table exists.

        readonly=False:
            Create the database and disposable benchmark tables.
        """

        if self.readonly:
            result = self.client.query(
                """
                SELECT count()
                FROM system.tables
                WHERE database = 'tensoryze'
                  AND name = 'processexecution'
                """
            )

            exists = result.result_rows[0][0]

            if exists != 1:
                raise RuntimeError(
                    "readonly=True but "
                    "tensoryze.processexecution does not exist."
                )

            return

        # --------------------------------------------------
        # Synthetic/disposable mode
        # --------------------------------------------------

        self.client.command(
            "CREATE DATABASE IF NOT EXISTS tensoryze"
        )

        self.client.command(
            """
            CREATE TABLE IF NOT EXISTS tensoryze.processexecution
            (
                id String,
                hash String,
                `timestamp` DateTime64(6),
                time_key String,
                date_key String,
                namespace_id String,
                _value Float32,
                _field String,
                _value_str String,
                created_at DateTime64(6),
                updated_at DateTime64(6),
                part_variant_id String
            )
            ENGINE = MergeTree
            PARTITION BY toYYYYMM(`timestamp`)
            ORDER BY (id, `timestamp`)
            """
        )

        self.client.command(
            """
            CREATE TABLE IF NOT EXISTS tensoryze.namespace
            (
                id String,
                label String
            )
            ENGINE = MergeTree
            ORDER BY id
            """
        )

        self.client.command(
            """
            CREATE TABLE IF NOT EXISTS tensoryze.partquality
            (
                hash String,
                `timestamp` DateTime64(6),
                part_id String,
                id String,
                time_key String,
                date_key String,
                namespace_id String,
                part_variant_id String,
                quality Int32,
                rework Int32,
                last_station String,
                error_code String,
                created_at DateTime64(6),
                updated_at DateTime64(6)
            )
            ENGINE = MergeTree
            ORDER BY (part_id, `timestamp`)
            """
        )

    # --------------------------------------------------
    # Truncate
    # --------------------------------------------------

    def truncate(self):
        if self.readonly:
            raise RuntimeError(
                "Refusing to truncate tensoryze.processexecution: "
                "ClickHouse adapter is in readonly mode."
            )

        self.client.command(
            "TRUNCATE TABLE tensoryze.processexecution"
        )

        self.client.command(
            "TRUNCATE TABLE tensoryze.partquality"
        )

    # --------------------------------------------------
    # Synthetic inserts
    # --------------------------------------------------

    def insert_batch(self, rows: list[tuple]):
        """
        BaseAdapter rows:

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

        ClickHouse table additionally requires:
            hash
            created_at
            updated_at

        For the real 66M-row benchmark we DO NOT use this method.
        The real dataset should continue to be bulk-loaded separately.

        This method exists for synthetic benchmark mode.
        """

        if self.readonly:
            raise RuntimeError(
                "insert_batch() cannot be used in readonly mode."
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        expanded = []

        for row in rows:
            expanded.append(
                [
                    row[0],               # id
                    uuid.uuid4().hex,     # hash
                    row[1],               # timestamp
                    row[2],               # time_key
                    row[3],               # date_key
                    row[4],               # namespace_id
                    row[5],               # _value
                    row[6],               # _field
                    row[7] or "",         # _value_str
                    now,                  # created_at
                    now,                  # updated_at
                    row[8] or "",         # part_variant_id
                ]
            )

        self.client.insert(
            "tensoryze.processexecution",
            expanded,
            column_names=[
                "id",
                "hash",
                "timestamp",
                "time_key",
                "date_key",
                "namespace_id",
                "_value",
                "_field",
                "_value_str",
                "created_at",
                "updated_at",
                "part_variant_id",
            ],
        )

    def insert_namespaces(self, rows: list[tuple]):
        """
        rows:
            (id, label)
        """

        if self.readonly:
            raise RuntimeError(
                "insert_namespaces() cannot be used in readonly mode."
            )

        if not rows:
            return

        self.client.insert(
            "tensoryze.namespace",
            [list(row) for row in rows],
            column_names=["id", "label"],
        )

    # --------------------------------------------------
    # Queries
    # --------------------------------------------------

    def run_query(self, sql_or_query, params=None):
        """
        Execute one ClickHouse query and return:

            (result, elapsed_seconds)

        Timing includes:
            ClickHouse execution
            +
            result transfer/materialization into Python

        This matches the behavior of the existing PostgreSQL and
        StarRocks adapters, where fetchall()/result retrieval is
        included in the benchmark time.

        IMPORTANT:
        ClickHouse query parameters should use ClickHouse-style
        placeholders such as:

            {part_ids:Array(String)}

        rather than PostgreSQL %s placeholders.

        Example:

            WHERE id IN {part_ids:Array(String)}

        params would then be:

            {"part_ids": ["id1", "id2"]}
        """

        start = time.perf_counter()

        if params:
            result = self.client.query(
                sql_or_query,
                parameters=params,
            )
        else:
            result = self.client.query(sql_or_query)

        rows = result.result_rows

        elapsed = time.perf_counter() - start

        return rows, elapsed

    # --------------------------------------------------
    # Row count
    # --------------------------------------------------

    def row_count(self) -> int:
        result = self.client.query(
            """
            SELECT count()
            FROM tensoryze.processexecution
            """
        )

        return int(result.result_rows[0][0])

    # --------------------------------------------------
    # Storage size
    # --------------------------------------------------

    def storage_size_mb(self) -> float:
        """
        ClickHouse stores MergeTree data as active data parts.

        system.parts.bytes_on_disk gives the total on-disk size
        of each part, so summing active parts gives the physical
        table footprint.

        This includes compressed column data, indexes, marks,
        and other part-level files.
        """

        result = self.client.query(
            """
            SELECT coalesce(sum(bytes_on_disk), 0)
            FROM system.parts
            WHERE database = 'tensoryze'
              AND table = 'processexecution'
              AND active
            """
        )

        size_bytes = int(result.result_rows[0][0])

        return round(
            size_bytes / (1024 * 1024),
            2
        )