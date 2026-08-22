#!/bin/bash
set -euo pipefail

DATA_DIR="/data"
RESULTS="/results/ingestion_results.csv"

HOST="postgres"
PORT="5432"
DATABASE="warehouse_restore"
USER="admin"
PASSWORD="admin"

TABLE="uns.sparkplug_metrics_ingest"

EXPECTED_ROWS=40000000
CHUNKS=8

export PGPASSWORD="$PASSWORD"

echo "=========================================="
echo "PostgreSQL ingestion benchmark"
echo "=========================================="

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
        echo "ERROR: Expected 5,000,000 rows."
        exit 1
    fi

    TOTAL_SOURCE_ROWS=$((TOTAL_SOURCE_ROWS + ROWS))
done

if [ "$TOTAL_SOURCE_ROWS" -ne "$EXPECTED_ROWS" ]; then
    echo "ERROR: Expected $EXPECTED_ROWS source rows."
    exit 1
fi

CURRENT_ROWS=$(psql \
    -h "$HOST" \
    -p "$PORT" \
    -U "$USER" \
    -d "$DATABASE" \
    -At \
    -c "SELECT COUNT(*) FROM $TABLE;")

if [ "$CURRENT_ROWS" -ne 0 ]; then
    echo "ERROR: $TABLE contains $CURRENT_ROWS rows."
    echo "Truncate the table before rerunning."
    exit 1
fi

START=$(date +%s.%N)

for N in $(seq 1 "$CHUNKS"); do
    I=$(printf "%02d" "$N")
    FILE="$DATA_DIR/sparkplug_metrics_${I}.csv"

    echo "Loading chunk $I / $CHUNKS"

    psql \
        -h "$HOST" \
        -p "$PORT" \
        -U "$USER" \
        -d "$DATABASE" \
        -v ON_ERROR_STOP=1 \
        -c "
        COPY $TABLE (
            \"timestamp\",
            namespace_id,
            field_id,
            value,
            text_value,
            event_id,
            sparkplug_message_type,
            properties
        )
        FROM STDIN
        WITH (FORMAT CSV);
        " < "$FILE"
done

END=$(date +%s.%N)

TOTAL=$(awk \
    -v start="$START" \
    -v end="$END" \
    'BEGIN {printf "%.3f", end-start}')

MINUTES=$(awk \
    -v seconds="$TOTAL" \
    'BEGIN {printf "%.2f", seconds/60}')

ROWS=$(psql \
    -h "$HOST" \
    -p "$PORT" \
    -U "$USER" \
    -d "$DATABASE" \
    -At \
    -c "SELECT COUNT(*) FROM $TABLE;")

if [ "$ROWS" -ne "$EXPECTED_ROWS" ]; then
    echo "ERROR: Expected $EXPECTED_ROWS rows, got $ROWS."
    exit 1
fi

RPS=$(awk \
    -v rows="$ROWS" \
    -v seconds="$TOTAL" \
    'BEGIN {printf "%.2f", rows/seconds}')

DATE=$(date +%Y-%m-%d)

echo
echo "=========================================="
echo "PostgreSQL ingestion complete"
echo "=========================================="
echo "Rows:       $ROWS"
echo "Seconds:    $TOTAL"
echo "Minutes:    $MINUTES"
echo "Rows/sec:   $RPS"
echo "=========================================="

if [ ! -f "$RESULTS" ]; then
    echo "Technology,Rows,Total_seconds,Total_minutes,Rows_per_second,Dataset,Date,Notes" \
        > "$RESULTS"
fi

echo "PostgreSQL,$ROWS,$TOTAL,$MINUTES,$RPS,sparkplug_metrics,$DATE,\"40M synthetic Sparkplug rows; 8x5M CSV chunks; COPY\"" \
    >> "$RESULTS"

echo "Saved to $RESULTS"