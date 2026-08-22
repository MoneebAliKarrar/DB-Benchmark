FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    bash \
    postgresql-client \
    default-mysql-client \
    curl \
    gawk \
    coreutils \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY entrypoint.sh /app/entrypoint.sh
COPY postgres.sh /app/postgres.sh
COPY timescaledb.sh /app/timescaledb.sh
COPY starrocks.sh /app/starrocks.sh

RUN chmod +x \
    /app/entrypoint.sh \
    /app/postgres.sh \
    /app/timescaledb.sh \
    /app/starrocks.sh

ENTRYPOINT ["/app/entrypoint.sh"]