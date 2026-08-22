#!/bin/bash
set -euo pipefail

TARGET="${1:-}"

case "$TARGET" in
    postgres)
        exec /app/postgres.sh
        ;;

    timescaledb)
        exec /app/timescaledb.sh
        ;;

    starrocks)
        exec /app/starrocks.sh
        ;;

    *)
        echo "Usage:"
        echo "  ingestion postgres"
        echo "  ingestion timescaledb"
        echo "  ingestion starrocks"
        exit 1
        ;;
esac