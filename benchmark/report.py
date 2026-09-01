import csv
import os
from datetime import datetime

# Column order matches the "Benchmark Results" sheet in FAPS_TSDB_Comparison.xlsx
# so rows can be pasted straight in.
HEADER = [
    "Technology", "Table Size (rows)", "Query / Test Type", "Metric",
    "Value", "Unit", "VM Config", "Date Tested", "Notes",
]


def init_results_file(results_dir: str, target: str) -> str:
    os.makedirs(results_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(results_dir, f"{target}_{timestamp}.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
    return path


def append_result(path: str, technology, table_size, query_type, metric,
                   value, unit, vm_config, date_tested, notes):
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([technology, table_size, query_type, metric, value, unit, vm_config, date_tested, notes])
