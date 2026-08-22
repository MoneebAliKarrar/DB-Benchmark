#!/bin/bash
set -euo pipefail

DATA_DIR="/data"
RESULTS="/results/ingestion_results.csv"

FE="tsdb_starrocks_fe"
HTTP_PORT="8030"
MYSQL_PORT="9030"

USER="root"
PASSWORD=""

DATABASE="monitoring"
TABLE="sparkplug_metrics_ingest"

EXPECTED_ROWS=40000000
CHUNKS=8

echo "=========================================="
echo "StarRocks ingestion benchmark"
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
# Verify target table exists
# --------------------------------------------------

TABLE_EXISTS=$(
    mysql \
        -h "$FE" \
        -P "$MYSQL_PORT" \
        -u "$USER" \
        -N -s \
        -e "
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema='$DATABASE'
          AND table_name='$TABLE';
        "
)

if [ "$TABLE_EXISTS" -ne 1 ]; then
    echo "ERROR: $DATABASE.$TABLE does not exist."
    exit 1
fi

# --------------------------------------------------
# Verify target is empty
# --------------------------------------------------

CURRENT_ROWS=$(
    mysql \
        -h "$FE" \
        -P "$MYSQL_PORT" \
        -u "$USER" \
        -N -s \
        -e "
        SELECT COUNT(*)
        FROM $DATABASE.$TABLE;
        "
)

echo "Current target rows: $CURRENT_ROWS"

if [ "$CURRENT_ROWS" -ne 0 ]; then
    echo "ERROR: Target contains $CURRENT_ROWS rows."
    echo "Truncate the table before rerunning."
    exit 1
fi

# --------------------------------------------------
# Start benchmark
# --------------------------------------------------

echo
echo "=========================================="
echo "Starting StarRocks ingestion"
echo "Rows:   $EXPECTED_ROWS"
echo "Chunks: $CHUNKS"
echo "=========================================="
echo

START=$(date +%s.%N)

TOTAL_LOADED=0
TOTAL_FILTERED=0

for N in $(seq 1 "$CHUNKS"); do

    I=$(printf "%02d" "$N")
    FILE="$DATA_DIR/sparkplug_metrics_${I}.csv"

    echo "------------------------------------------"
    echo "Loading chunk $I / $CHUNKS"
    echo "$FILE"
    echo "------------------------------------------"

    RESPONSE=$(
        curl -s \
            --location-trusted \
            -u "$USER:$PASSWORD" \
            -H "column_separator:," \
            -H 'enclose:"' \
            -H 'escape:\' \
            -H "format:csv" \
            -H "timeout:3600" \
            -H "max_filter_ratio:0" \
            -T "$FILE" \
            "http://$FE:$HTTP_PORT/api/$DATABASE/$TABLE/_stream_load"
    )

    echo "$RESPONSE"

    # --------------------------------------------------
    # Validate Stream Load status
    # --------------------------------------------------

    if ! echo "$RESPONSE" | grep -q '"Status": "Success"'; then
        echo
        echo "ERROR: Stream Load failed for:"
        echo "$FILE"
        exit 1
    fi

    LOADED=$(
        echo "$RESPONSE" \
        | grep -o '"NumberLoadedRows":[[:space:]]*[0-9]*' \
        | grep -o '[0-9]*' \
        | head -1
    )

    FILTERED=$(
        echo "$RESPONSE" \
        | grep -o '"NumberFilteredRows":[[:space:]]*[0-9]*' \
        | grep -o '[0-9]*' \
        | head -1
    )

    LOADED="${LOADED:-0}"
    FILTERED="${FILTERED:-0}"

    echo "Loaded rows:   $LOADED"
    echo "Filtered rows: $FILTERED"

    if [ "$LOADED" -ne 5000000 ]; then
        echo
        echo "ERROR: Expected 5,000,000 loaded rows."
        echo "Actual: $LOADED"
        exit 1
    fi

    if [ "$FILTERED" -ne 0 ]; then
        echo
        echo "ERROR: StarRocks filtered $FILTERED rows."
        exit 1
    fi

    TOTAL_LOADED=$((TOTAL_LOADED + LOADED))
    TOTAL_FILTERED=$((TOTAL_FILTERED + FILTERED))

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
# Verify final row count
# --------------------------------------------------

ROWS=$(
    mysql \
        -h "$FE" \
        -P "$MYSQL_PORT" \
        -u "$USER" \
        -N -s \
        -e "
        SELECT COUNT(*)
        FROM $DATABASE.$TABLE;
        "
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
echo "StarRocks ingestion benchmark complete"
echo "=========================================="
echo "Rows loaded:    $ROWS"
echo "Seconds:        $TOTAL"
echo "Minutes:        $MINUTES"
echo "Rows/sec:       $RPS"
echo "Filtered rows:  $TOTAL_FILTERED"
echo "=========================================="

# --------------------------------------------------
# Save result
# --------------------------------------------------

if [ ! -f "$RESULTS" ]; then
    echo "Technology,Rows,Total_seconds,Total_minutes,Rows_per_second,Dataset,Date,Notes" \
        > "$RESULTS"
fi

echo "StarRocks,$ROWS,$TOTAL,$MINUTES,$RPS,sparkplug_metrics,$DATE,\"40M synthetic Sparkplug rows; 8x5M CSV chunks; Stream Load; filtered=$TOTAL_FILTERED; sequential loads\"" \
    >> "$RESULTS"

echo
echo "Result saved to:"
echo "$RESULTS"