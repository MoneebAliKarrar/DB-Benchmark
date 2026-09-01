#!/bin/bash
set -euo pipefail

DATA_DIR="/data"
RESULTS="/results/ingestion_results.csv"

HOST="tsdb_clickhouse"
HTTP_PORT="8123"

USER="admin"
PASSWORD="admin"

DATABASE="monitoring"
TABLE="sparkplug_metrics_ingest"

EXPECTED_ROWS=40000000
CHUNKS=8

echo "=========================================="
echo "ClickHouse ingestion benchmark"
echo "=========================================="

# --------------------------------------------------
# Validate source CSV files
# --------------------------------------------------

TOTAL_SOURCE_ROWS=0

for N in $(seq 1 "$CHUNKS"); do
    I=$(printf "%02d" "$N")
    FILE="$DATA_DIR/sparkplug_metrics_${I}.csv"

    if [ ! -f "$FILE" ]; then
        echo "ERROR: Missing $FILE"
        exit 1
    fi

    ROWS=$(wc -l < "$FILE")

    echo "Chunk $I: $ROWS rows"

    if [ "$ROWS" -ne 5000000 ]; then
        echo "ERROR: Expected 5,000,000 rows in $FILE"
        echo "Found: $ROWS"
        exit 1
    fi

    TOTAL_SOURCE_ROWS=$((TOTAL_SOURCE_ROWS + ROWS))
done

echo "Total source rows: $TOTAL_SOURCE_ROWS"

if [ "$TOTAL_SOURCE_ROWS" -ne "$EXPECTED_ROWS" ]; then
    echo "ERROR: Expected $EXPECTED_ROWS total source rows."
    exit 1
fi

# --------------------------------------------------
# Check ClickHouse connection
# --------------------------------------------------

echo
echo "Checking ClickHouse connection..."

CONNECTION_TEST=$(
    curl -sS \
        -u "$USER:$PASSWORD" \
        "http://$HOST:$HTTP_PORT/?query=SELECT%201"
)

if [ "$CONNECTION_TEST" != "1" ]; then
    echo "ERROR: Could not connect to ClickHouse."
    echo "Response: $CONNECTION_TEST"
    exit 1
fi

echo "ClickHouse connection OK."

# --------------------------------------------------
# Verify target table exists
# --------------------------------------------------

TABLE_EXISTS=$(
    curl -sS \
        -u "$USER:$PASSWORD" \
        --data-binary "
        SELECT count()
        FROM system.tables
        WHERE database = '$DATABASE'
          AND name = '$TABLE'
        FORMAT TabSeparatedRaw
        " \
        "http://$HOST:$HTTP_PORT/"
)

if [ "$TABLE_EXISTS" -ne 1 ]; then
    echo "ERROR: $DATABASE.$TABLE does not exist."
    exit 1
fi

# --------------------------------------------------
# Verify target is empty
# --------------------------------------------------

CURRENT_ROWS=$(
    curl -sS \
        -u "$USER:$PASSWORD" \
        --data-binary "
        SELECT count()
        FROM $DATABASE.$TABLE
        FORMAT TabSeparatedRaw
        " \
        "http://$HOST:$HTTP_PORT/"
)

echo "Current target rows: $CURRENT_ROWS"

if [ "$CURRENT_ROWS" -ne 0 ]; then
    echo
    echo "ERROR: Target contains $CURRENT_ROWS rows."
    echo "Truncate the table before rerunning."
    exit 1
fi

# --------------------------------------------------
# Start benchmark
# --------------------------------------------------

echo
echo "=========================================="
echo "Starting ClickHouse ingestion"
echo "Rows:   $EXPECTED_ROWS"
echo "Chunks: $CHUNKS"
echo "=========================================="
echo

START=$(date +%s.%N)

for N in $(seq 1 "$CHUNKS"); do
    I=$(printf "%02d" "$N")
    FILE="$DATA_DIR/sparkplug_metrics_${I}.csv"

    echo "------------------------------------------"
    echo "Loading chunk $I / $CHUNKS"
    echo "$FILE"
    echo "------------------------------------------"

    curl -sS \
        --fail-with-body \
        -u "$USER:$PASSWORD" \
        -H "Content-Type: text/plain" \
        --data-binary @"$FILE" \
        "http://$HOST:$HTTP_PORT/?query=INSERT%20INTO%20$DATABASE.$TABLE%20FORMAT%20CSV"

    echo
    echo "Chunk $I loaded successfully."
done

END=$(date +%s.%N)

# --------------------------------------------------
# Calculate timing
# --------------------------------------------------

TOTAL=$(awk \
    -v start="$START" \
    -v end="$END" \
    'BEGIN {printf "%.3f", end-start}')

MINUTES=$(awk \
    -v seconds="$TOTAL" \
    'BEGIN {printf "%.2f", seconds/60}')

# --------------------------------------------------
# Verify final count
# --------------------------------------------------

ROWS=$(
    curl -sS \
        -u "$USER:$PASSWORD" \
        --data-binary "
        SELECT count()
        FROM $DATABASE.$TABLE
        FORMAT TabSeparatedRaw
        " \
        "http://$HOST:$HTTP_PORT/"
)

if [ "$ROWS" -ne "$EXPECTED_ROWS" ]; then
    echo
    echo "ERROR: Final row count is incorrect."
    echo "Expected: $EXPECTED_ROWS"
    echo "Actual:   $ROWS"
    exit 1
fi

# --------------------------------------------------
# Calculate throughput
# --------------------------------------------------

RPS=$(awk \
    -v rows="$ROWS" \
    -v seconds="$TOTAL" \
    'BEGIN {printf "%.2f", rows/seconds}')

DATE=$(date +%Y-%m-%d)

# --------------------------------------------------
# Display result
# --------------------------------------------------

echo
echo "=========================================="
echo "ClickHouse ingestion benchmark complete"
echo "=========================================="
echo "Rows loaded:    $ROWS"
echo "Seconds:        $TOTAL"
echo "Minutes:        $MINUTES"
echo "Rows/sec:       $RPS"
echo "=========================================="

# --------------------------------------------------
# Save result
# --------------------------------------------------

if [ ! -f "$RESULTS" ]; then
    echo "Technology,Rows,Total_seconds,Total_minutes,Rows_per_second,Dataset,Date,Notes" \
        > "$RESULTS"
fi

echo "ClickHouse,$ROWS,$TOTAL,$MINUTES,$RPS,sparkplug_metrics,$DATE,\"40M synthetic Sparkplug rows; 8x5M CSV chunks; HTTP INSERT FORMAT CSV; sequential loads\"" \
    >> "$RESULTS"

echo
echo "Result saved to:"
echo "$RESULTS"