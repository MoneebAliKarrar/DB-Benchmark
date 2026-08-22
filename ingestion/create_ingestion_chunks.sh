#!/bin/bash
set -euo pipefail

PROJECT="$HOME/DB-Benchmark-Research"
DATA_DIR="$PROJECT/data/starrocks"

mkdir -p "$DATA_DIR"

# Last hash already included in processexecution_01.csv
BOUNDARY='1179053076019229931'

START_CHUNK=2
END_CHUNK=8

for CHUNK in $(seq "$START_CHUNK" "$END_CHUNK"); do
    FILE=$(printf "$DATA_DIR/processexecution_%02d.csv" "$CHUNK")

    echo
    echo "=========================================="
    echo "Creating chunk $CHUNK"
    echo "Starting after hash: $BOUNDARY"
    echo "=========================================="

    docker exec tsdb_postgres \
        psql -U admin -d warehouse_restore -At -c "
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
            FROM tensoryze.processexecution
            WHERE hash > '$BOUNDARY'
            ORDER BY hash
            LIMIT 5000000
        ) TO STDOUT WITH CSV;
        " > "$FILE"

    ROWS=$(wc -l < "$FILE")

    echo "Rows exported: $ROWS"

    if [ "$ROWS" -eq 0 ]; then
        echo "ERROR: No rows exported."
        rm -f "$FILE"
        exit 1
    fi

    if [ "$ROWS" -ne 5000000 ]; then
        echo "WARNING: Expected 5,000,000 rows but got $ROWS"
    fi

    # hash is the second CSV column
    BOUNDARY=$(tail -n 1 "$FILE" | cut -d',' -f2)

    echo "New boundary: $BOUNDARY"
    echo "Saved: $FILE"
done

echo
echo "=========================================="
echo "Chunk creation complete"
echo "=========================================="

wc -l "$DATA_DIR"/processexecution_0{1..8}.csv