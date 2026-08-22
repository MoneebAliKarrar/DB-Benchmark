import os

# --- Table sizes to test at (rows in tensoryze.processexecution).
TABLE_SIZES = [
    100_000,
    1_000_000,
    10_000_000,
    # 100_000_000,   
]

# --- Synthetic data shape. Each "part" produced on the line gets one
# reading per namespace/field (mimics processexecution's one-row-per-
# measurement layout). Update these once you know FAPS's real cardinality
# (how many distinct namespaces/parameters per part in production). ---
PART_ID_PREFIX = "SPM26"
FIELD_NAMES = [
    "final_force", "temperature", "pressure", "torque", "speed",
    "vibration", "humidity", "current", "voltage", "cycle_time",
]
NUM_NAMESPACES = len(FIELD_NAMES)  # 1 namespace <-> 1 field/parameter, matching Q4's GROUP BY n.label
INSERT_BATCH_SIZE = 50_000

# Fraction of generated parts inserted into tensoryze.partquality
# (drives query 1 - "source read feeding part_traceability").
QUALITY_SAMPLE_RATIO = 1.0

# How many sample part IDs to pull for the "per-part read" query (query 2
# in Tim's file needed 3 concrete IDs in place of the placeholders).
SAMPLE_PART_ID_COUNT = 3

# --- How many times to repeat each query for a stable latency reading ---
QUERY_REPEATS = 5

# --- Connection settings ---
POSTGRES_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "host.docker.internal"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname": os.getenv("POSTGRES_DB", "warehouse_restore"),
    "user": os.getenv("POSTGRES_USER", "admin"),
    "password": os.getenv("POSTGRES_PASSWORD", "admin"),
}

TIMESCALEDB_CONFIG = {
    "host": os.getenv("TIMESCALE_HOST", "host.docker.internal"),
    "port": int(os.getenv("TIMESCALE_PORT", 5433)),
    "dbname": os.getenv("TIMESCALE_DB", "warehouse_restore"),
    "user": os.getenv("TIMESCALE_USER", "admin"),
    "password": os.getenv("TIMESCALE_PASSWORD", "admin"),
}

# --- Where results get written ---
RESULTS_DIR = "results"
VM_CONFIG_LABEL = "VM Config,8 vCPU / 251GiB RAM (no Docker memory limit)"  


STARROCKS_CONFIG = {
    "host": "starrocks-fe",
    "port": 9030,
    "user": "root",
    "password": "",
    "database": "tensoryze",
}