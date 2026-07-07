# syntax=docker/dockerfile:1

FROM --platform=linux/amd64 ubuntu:26.04 AS app

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --chmod=0555 dist/chall ./chall
COPY --chmod=0444 service/flag.txt ./flag.txt

COPY <<'EOF' /app/run
#!/bin/sh
set -eu

cd /app
exec ./chall
EOF

RUN chmod 0555 /app/chall /app/run \
    && chmod 0444 /app/flag.txt \
    && chown -R root:root /app

FROM --platform=linux/amd64 pwn.red/jail@sha256:b6cf7d734b58b8008ec202d4c8329e95d70907e0a10436c314405dc3b1f6e304

COPY --from=app / /srv

ENV JAIL_PORT=1337 \
    JAIL_TIME=10800 \
    JAIL_PIDS=64 \
    JAIL_MEM=256M \
    JAIL_CPU=500 \
    JAIL_TMP_SIZE=16M
