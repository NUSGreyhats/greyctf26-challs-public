#!/bin/sh
set -eu

export APP_HOST="${APP_HOST:-0.0.0.0}"
export APP_PORT="${APP_PORT:-8000}"

export PGBOUNCER_DB_HOST="${PGBOUNCER_DB_HOST:-db}"
export PGBOUNCER_DB_PORT="${PGBOUNCER_DB_PORT:-5432}"
export PGBOUNCER_DB_NAME="${PGBOUNCER_DB_NAME:-go_going_goen}"
export PGBOUNCER_DB_USER="${PGBOUNCER_DB_USER:-postgres}"
export PGBOUNCER_DB_PASSWORD="${PGBOUNCER_DB_PASSWORD:-postgres}"

export PGBOUNCER_LISTEN_PORT="${PGBOUNCER_LISTEN_PORT:-0}"
export PGBOUNCER_POOL_MODE="${PGBOUNCER_POOL_MODE:-transaction}"
export PGBOUNCER_MAX_CLIENT_CONN="${PGBOUNCER_MAX_CLIENT_CONN:-1000}"
export PGBOUNCER_DEFAULT_POOL_SIZE="${PGBOUNCER_DEFAULT_POOL_SIZE:-200}"
export PGBOUNCER_MIN_POOL_SIZE="${PGBOUNCER_MIN_POOL_SIZE:-0}"
export PGBOUNCER_RESERVE_POOL_SIZE="${PGBOUNCER_RESERVE_POOL_SIZE:-0}"
export PGBOUNCER_QUERY_WAIT_TIMEOUT="${PGBOUNCER_QUERY_WAIT_TIMEOUT:-120}"
export PGBOUNCER_CLIENT_IDLE_TIMEOUT="${PGBOUNCER_CLIENT_IDLE_TIMEOUT:-60}"
export PGBOUNCER_SERVER_IDLE_TIMEOUT="${PGBOUNCER_SERVER_IDLE_TIMEOUT:-30}"
export PGBOUNCER_SERVER_LIFETIME="${PGBOUNCER_SERVER_LIFETIME:-600}"
export PGBOUNCER_CLIENT_USER="${PGBOUNCER_CLIENT_USER:-${PGBOUNCER_DB_USER}}"
export PGBOUNCER_CLIENT_PASSWORD="${PGBOUNCER_CLIENT_PASSWORD:-${PGBOUNCER_DB_PASSWORD}}"

if [ "${PGBOUNCER_LISTEN_PORT}" = "0" ]; then
    PGBOUNCER_LISTEN_PORT=$(python - <<'PY'
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)
    export PGBOUNCER_LISTEN_PORT
fi

export DATABASE_URL="postgresql+psycopg://${PGBOUNCER_CLIENT_USER}:${PGBOUNCER_CLIENT_PASSWORD}@127.0.0.1:${PGBOUNCER_LISTEN_PORT}/${PGBOUNCER_DB_NAME}"

envsubst < /etc/pgbouncer/pgbouncer.ini.template > /etc/pgbouncer/pgbouncer.ini
printf '"%s" "%s"\n' "${PGBOUNCER_CLIENT_USER}" "${PGBOUNCER_CLIENT_PASSWORD}" > /etc/pgbouncer/userlist.txt
chown pgbouncer:pgbouncer /etc/pgbouncer/pgbouncer.ini /etc/pgbouncer/userlist.txt
chmod 0640 /etc/pgbouncer/pgbouncer.ini /etc/pgbouncer/userlist.txt

echo "Starting backend bundle: app listens on ${APP_HOST}:${APP_PORT}; database endpoint is 127.0.0.1:${PGBOUNCER_LISTEN_PORT}/${PGBOUNCER_DB_NAME}; PgBouncer upstream is ${PGBOUNCER_DB_HOST}:${PGBOUNCER_DB_PORT}/${PGBOUNCER_DB_NAME}"

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
