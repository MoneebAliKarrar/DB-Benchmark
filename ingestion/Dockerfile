FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    bash \
    python3 \
    python3-psycopg2 \
    postgresql-client \
    default-mysql-client \
    curl \
    gawk \
    coreutils \
    ca-certificates \
    python3-pymysql \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages clickhouse-connect

WORKDIR /app

COPY entrypoint.sh /app/entrypoint.sh
COPY postgres.sh /app/postgres.sh
COPY timescaledb.sh /app/timescaledb.sh
COPY starrocks.sh /app/starrocks.sh
COPY clickhouse.sh /app/clickhouse.sh
COPY postgres.py /app/postgres.py
COPY timescaledb.py /app/timescaledb.py
COPY starrocks.py /app/starrocks.py
COPY clickhouse.py /app/clickhouse.py

RUN chmod +x \
    /app/entrypoint.sh \
    /app/postgres.sh \
    /app/timescaledb.sh \
    /app/starrocks.sh \
    /app/clickhouse.sh

ENTRYPOINT ["/app/entrypoint.sh"]