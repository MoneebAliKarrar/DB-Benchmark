import time
import connectorx as cx


def benchmark_connectorx(
    db_url: str,
    query: str
):
    start = time.perf_counter()

    df = cx.read_sql(
        db_url,
        query
    )

    elapsed = time.perf_counter() - start

    rows = len(df)

    return {
        "rows": rows,
        "seconds": elapsed,
        "rows_per_second": rows / elapsed
    }