    #!/bin/bash
    set -euo pipefail

    PROJECT="$HOME/DB-Benchmark-Research"
    TEMP_DIR="$PROJECT/data/clickhouse_load"

    PG_CONTAINER="tsdb_postgres"
    PG_DATABASE="warehouse_restore"
    PG_USER="admin"

    CH_CONTAINER="tsdb_clickhouse"
    CH_USER="admin"
    CH_PASSWORD="admin"

    SOURCE_TABLE="tensoryze.processexecution"
    TARGET_TABLE="tensoryze.processexecution"

    EXPECTED_ROWS=66156940
    CHUNK_SIZE=5000000

    mkdir -p "$TEMP_DIR"

    echo "=========================================="
    echo "Full PostgreSQL -> ClickHouse reload"
    echo "Expected rows: $EXPECTED_ROWS"
    echo "Chunk size:    $CHUNK_SIZE"
    echo "=========================================="

    # --------------------------------------------------
    # Verify source
    # --------------------------------------------------

    SOURCE_ROWS=$(docker exec "$PG_CONTAINER" \
        psql -U "$PG_USER" -d "$PG_DATABASE" -At -c \
        "SELECT COUNT(*) FROM $SOURCE_TABLE;")

    echo "PostgreSQL source rows: $SOURCE_ROWS"

    if [ "$SOURCE_ROWS" -ne "$EXPECTED_ROWS" ]; then
        echo "ERROR: Unexpected PostgreSQL row count."
        exit 1
    fi

    # --------------------------------------------------
    # Verify ClickHouse is empty
    # --------------------------------------------------

    TARGET_ROWS=$(docker exec "$CH_CONTAINER" \
        clickhouse-client \
        --user "$CH_USER" \
        --password "$CH_PASSWORD" \
        --query="SELECT count() FROM $TARGET_TABLE")

    echo "ClickHouse current rows: $TARGET_ROWS"

    if [ "$TARGET_ROWS" -ne 0 ]; then
        echo "ERROR: ClickHouse target is not empty."
        echo "Run:"
        echo "TRUNCATE TABLE $TARGET_TABLE"
        exit 1
    fi

    # --------------------------------------------------
    # Start loading
    # --------------------------------------------------

    BOUNDARY=""
    CHUNK=1
    TOTAL_EXPORTED=0

    START=$(date +%s.%N)

    while true; do

        FILE=$(printf "$TEMP_DIR/processexecution_%02d.csv" "$CHUNK")

        echo
        echo "=========================================="
        echo "Chunk $CHUNK"
        echo "=========================================="

        if [ -z "$BOUNDARY" ]; then

            echo "Exporting first $CHUNK_SIZE rows..."

            docker exec "$PG_CONTAINER" \
                psql -U "$PG_USER" -d "$PG_DATABASE" -At -c "
                COPY (
                    SELECT
                        id,
                        hash,
                        \"timestamp\",
                        time_key,
                        date_key,
                        namespace_id,
                        _value,
                        _field,
                        _value_str,
                        created_at,
                        updated_at,
                        part_variant_id
                    FROM $SOURCE_TABLE
                    ORDER BY hash
                    LIMIT $CHUNK_SIZE
                )
                TO STDOUT WITH CSV;
                " > "$FILE"

        else

            echo "Exporting after hash:"
            echo "$BOUNDARY"

            docker exec "$PG_CONTAINER" \
                psql -U "$PG_USER" -d "$PG_DATABASE" -At -c "
                COPY (
                    SELECT
                        id,
                        hash,
                        \"timestamp\",
                        time_key,
                        date_key,
                        namespace_id,
                        _value,
                        _field,
                        _value_str,
                        created_at,
                        updated_at,
                        part_variant_id
                    FROM $SOURCE_TABLE
                    WHERE hash > '$BOUNDARY'
                    ORDER BY hash
                    LIMIT $CHUNK_SIZE
                )
                TO STDOUT WITH CSV;
                " > "$FILE"

        fi

        ROWS=$(wc -l < "$FILE")

        echo "Exported rows: $ROWS"

        # No data left
        if [ "$ROWS" -eq 0 ]; then
            rm -f "$FILE"
            break
        fi

        TOTAL_EXPORTED=$((TOTAL_EXPORTED + ROWS))

        # --------------------------------------------------
        # Load into ClickHouse
        # --------------------------------------------------

        echo "Loading into ClickHouse..."

        docker exec -i "$CH_CONTAINER" \
            clickhouse-client \
            --user "$CH_USER" \
            --password "$CH_PASSWORD" \
            --query="INSERT INTO $TARGET_TABLE FORMAT CSV" \
            < "$FILE"

        echo "ClickHouse load successful."

        # --------------------------------------------------
        # Move hash boundary
        # --------------------------------------------------

        BOUNDARY=$(tail -n 1 "$FILE" | cut -d',' -f2)

        echo "New boundary: $BOUNDARY"
        echo "Total exported so far: $TOTAL_EXPORTED"

        # We don't need the temporary file anymore.
        rm -f "$FILE"

        # --------------------------------------------------
        # Verify progress
        # --------------------------------------------------

        CURRENT_ROWS=$(docker exec "$CH_CONTAINER" \
            clickhouse-client \
            --user "$CH_USER" \
            --password "$CH_PASSWORD" \
            --query="SELECT count() FROM $TARGET_TABLE")

        echo "ClickHouse rows now: $CURRENT_ROWS"

        if [ "$CURRENT_ROWS" -eq "$EXPECTED_ROWS" ]; then
            echo "Expected row count reached."
            break
        fi

        if [ "$CURRENT_ROWS" -gt "$EXPECTED_ROWS" ]; then
            echo "ERROR: ClickHouse has more rows than expected!"
            exit 1
        fi

        CHUNK=$((CHUNK + 1))
    done

    END=$(date +%s.%N)

    # --------------------------------------------------
    # Final validation
    # --------------------------------------------------

    FINAL_ROWS=$(docker exec "$CH_CONTAINER" \
        clickhouse-client \
        --user "$CH_USER" \
        --password "$CH_PASSWORD" \
        --query="SELECT count() FROM $TARGET_TABLE")

    SECONDS=$(awk -v start="$START" -v end="$END" \
        'BEGIN {printf "%.3f", end-start}')

    MINUTES=$(awk -v seconds="$SECONDS" \
        'BEGIN {printf "%.2f", seconds/60}')

    echo
    echo "=========================================="
    echo "Full ClickHouse reload complete"
    echo "=========================================="
    echo "PostgreSQL rows: $SOURCE_ROWS"
    echo "ClickHouse rows: $FINAL_ROWS"
    echo "Seconds:         $SECONDS"
    echo "Minutes:         $MINUTES"
    echo "=========================================="

    if [ "$FINAL_ROWS" -ne "$EXPECTED_ROWS" ]; then
        echo "ERROR: Final ClickHouse row count does not match PostgreSQL."
        exit 1
    fi

    echo "SUCCESS: all $EXPECTED_ROWS rows loaded."