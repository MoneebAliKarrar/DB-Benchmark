from abc import ABC, abstractmethod


class BaseAdapter(ABC):
    """
    Common interface every database adapter must implement.
    benchmark.py only talks to this interface, so adding a new database
    later (ClickHouse, IoTDB...) means writing one new adapter file, not
    touching the benchmark loop itself.
    """

    name: str = "base"

    @abstractmethod
    def connect(self):
        """Open a connection / client."""
        raise NotImplementedError

    @abstractmethod
    def close(self):
        """Close the connection / client cleanly."""
        raise NotImplementedError

    @abstractmethod
    def setup(self):
        """Create schema/table if needed (idempotent)."""
        raise NotImplementedError

    @abstractmethod
    def truncate(self):
        """Wipe existing data before loading a fresh batch of a given size."""
        raise NotImplementedError

    @abstractmethod
    def insert_batch(self, rows: list[tuple]):
        """
        rows: (id, timestamp, time_key, date_key, namespace_id, value, field,
        value_str, part_variant_id) tuples, matching
        tensoryze.processexecution's columns.
        Should be efficient bulk insert, not row-by-row.
        """
        raise NotImplementedError

    @abstractmethod
    def insert_namespaces(self, rows: list[tuple]):
        """rows: list of (id, label) tuples for tensoryze.namespace."""
        raise NotImplementedError

    @abstractmethod
    def run_query(self, sql_or_query, params=None):
        """
        Execute a single query and return (result, elapsed_seconds).
        Timing must wrap only the query execution, not connection setup.
        """
        raise NotImplementedError

    @abstractmethod
    def row_count(self) -> int:
        """Return current row count in the table (sanity check after load)."""
        raise NotImplementedError

    @abstractmethod
    def storage_size_mb(self) -> float:
        """Return on-disk size of the table/data in MB."""
        raise NotImplementedError