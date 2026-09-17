import csv
import time
import statistics
import os
from datetime import date

import clickhouse_connect

HOST = "clickhouse"
PORT = 8123
DATABASE = "monitoring"
TABLE = "sparkplug_metrics_ingest"

FILE = "/data/sparkplug_metrics_01.csv"

BATCH_SIZE = 1
TOTAL_ROWS = 1_000_000

COLUMNS = [
    "timestamp",
    "namespace_id",
    "field_id",
    "value",
    "text_value",
    "event_id",
    "sparkplug_message_type",
    "properties",
]


def normalize(row):
    return [
        None if value == "" else value
        for value in row
    ]


USER = "admin"
PASSWORD = "admin"

client = clickhouse_connect.get_client(
    host=HOST,
    port=PORT,
    username=USER,
    password=PASSWORD,
    database=DATABASE,
)

current_rows = client.query(
    f"SELECT count() FROM {TABLE}"
).result_rows[0][0]

if current_rows != 0:
    raise RuntimeError(
        f"{DATABASE}.{TABLE} already contains {current_rows} rows. "
        "Truncate it before running the benchmark."
    )


batch = []
batch_times = []
inserted = 0

print("=" * 60)
print("ClickHouse continuous ingestion benchmark")
print(f"Batch size : {BATCH_SIZE}")
print(f"Total rows : {TOTAL_ROWS}")
print("=" * 60)

start_total = time.perf_counter()

with open(FILE, newline="") as f:
    reader = csv.reader(f)

    for row in reader:
        batch.append(normalize(row))

        if len(batch) >= BATCH_SIZE:
            start_batch = time.perf_counter()

            client.insert(
                TABLE,
                batch,
                column_names=COLUMNS,
                database=DATABASE,
            )

            elapsed = time.perf_counter() - start_batch
            batch_times.append(elapsed)

            inserted += len(batch)
            batch = []

            if inserted % 100_000 == 0:
                print(
                    f"Inserted {inserted:,}/{TOTAL_ROWS:,} rows"
                )

            if inserted >= TOTAL_ROWS:
                break


# Handle remaining rows if TOTAL_ROWS is not exactly divisible
# by the chosen batch size.
if batch and inserted < TOTAL_ROWS:
    remaining = TOTAL_ROWS - inserted
    batch = batch[:remaining]

    start_batch = time.perf_counter()

    client.insert(
        TABLE,
        batch,
        column_names=COLUMNS,
        database=DATABASE,
    )

    elapsed = time.perf_counter() - start_batch
    batch_times.append(elapsed)

    inserted += len(batch)


end_total = time.perf_counter()

total_seconds = end_total - start_total
rows_per_second = inserted / total_seconds

batch_ms = [
    elapsed * 1000
    for elapsed in batch_times
]

median_ms = statistics.median(batch_ms)

sorted_times = sorted(batch_ms)
p95_index = int(0.95 * (len(sorted_times) - 1))
p95_ms = sorted_times[p95_index]


RESULTS_FILE = "/results/continuous_ingestion_results.csv"

file_exists = os.path.isfile(RESULTS_FILE)

with open(RESULTS_FILE, "a", newline="") as f:
    writer = csv.writer(f)

    if not file_exists:
        writer.writerow([
            "Technology",
            "Rows",
            "Batch_size",
            "Number_of_batches",
            "Total_seconds",
            "Rows_per_second",
            "Median_batch_latency_ms",
            "P95_batch_latency_ms",
            "Dataset",
            "Date",
            "Notes"
        ])

    writer.writerow([
        "ClickHouse",
        inserted,
        BATCH_SIZE,
        len(batch_times),
        f"{total_seconds:.3f}",
        f"{rows_per_second:.2f}",
        f"{median_ms:.2f}",
        f"{p95_ms:.2f}",
        "sparkplug_metrics",
        date.today().isoformat(),
        "Continuous incremental ingestion; native client INSERT batches; synchronous batch acknowledgement"
    ])


print()
print(f"Saved to {RESULTS_FILE}")

print()
print("=" * 60)
print("RESULT")
print("=" * 60)
print(f"Rows inserted        : {inserted:,}")
print(f"Batch size           : {BATCH_SIZE:,}")
print(f"Number of batches    : {len(batch_times):,}")
print(f"Total seconds        : {total_seconds:.3f}")
print(f"Rows/sec             : {rows_per_second:.2f}")
print(f"Median batch latency : {median_ms:.2f} ms")
print(f"P95 batch latency    : {p95_ms:.2f} ms")
print("=" * 60)