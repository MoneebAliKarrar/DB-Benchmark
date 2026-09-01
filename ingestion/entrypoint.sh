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

    clickhouse)
        exec /app/clickhouse.sh
        ;;

    *)
        echo "Usage:"
        echo "  ingestion postgres"
        echo "  ingestion timescaledb"
        echo "  ingestion starrocks"
        echo "  ingestion clickhouse"
        exit 1
        ;;
esac