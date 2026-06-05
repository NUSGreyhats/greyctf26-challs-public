#!/bin/sh
set -eu

python - <<'PY'
import os
import socket
import sys
import time

host = "127.0.0.1"
port = int(os.environ.get("PGBOUNCER_LISTEN_PORT", "6432"))
deadline = time.monotonic() + int(os.environ.get("PGBOUNCER_STARTUP_TIMEOUT_SECONDS", "30"))

while True:
    try:
        with socket.create_connection((host, port), timeout=1):
            break
    except OSError:
        if time.monotonic() >= deadline:
            print(f"PgBouncer did not become ready on {host}:{port}", file=sys.stderr)
            sys.exit(1)
        time.sleep(0.2)
PY

exec uvicorn app.main:app \
    --host "${APP_HOST}" \
    --port "${APP_PORT}" \
    --limit-concurrency "${APP_LIMIT_CONCURRENCY:-300}" \
    --backlog "${APP_BACKLOG:-128}" \
    --timeout-keep-alive "${APP_TIMEOUT_KEEP_ALIVE:-5}"
