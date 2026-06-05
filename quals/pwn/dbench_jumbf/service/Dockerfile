FROM --platform=linux/amd64 debian:trixie-slim@sha256:486b1c3d3a6a836d2518d5ac1a7b522050a034ae83b47c063fd45d550b2b9dbf AS app

RUN apt-get update && \
    apt-get install -y --no-install-recommends libstdc++6 && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1000 ctf && \
    useradd --system --uid 1000 --gid 1000 --home-dir /nonexistent --shell /usr/sbin/nologin ctf

WORKDIR /app
COPY server ./server
COPY run /app/run
COPY flag.txt /flag.txt
COPY THIRD_PARTY_LICENSES.md /licenses/THIRD_PARTY_LICENSES.md
COPY dbench_jumbf/LICENSE.txt /licenses/dbench_jumbf_LICENSE.txt
RUN chmod 0555 /app/server /app/run && \
    chmod 0444 /flag.txt && \
    chown -R root:root /app /flag.txt /licenses

FROM --platform=linux/amd64 pwn.red/jail@sha256:b6cf7d734b58b8008ec202d4c8329e95d70907e0a10436c314405dc3b1f6e304

COPY --from=app / /srv

ENV JAIL_PORT=1337 \
    JAIL_TIME=60 \
    JAIL_PIDS=16 \
    JAIL_MEM=128M \
    JAIL_CPU=500 \
    JAIL_TMP_SIZE=0
