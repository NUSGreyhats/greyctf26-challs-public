#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INTEGRATION_DIR="$ROOT/dev/integration"
VENDOR_DIR="$INTEGRATION_DIR/vendor/ctfd-team-token-plugin"
COMPOSE="docker compose -p g26-q-integration -f $INTEGRATION_DIR/docker-compose.test.yml"
COMPOSE_PORT="$ROOT/scripts/compose-port.sh -p g26-q-integration -f $INTEGRATION_DIR/docker-compose.test.yml"

cd "$ROOT"

if [[ ! -d "$VENDOR_DIR/.git" ]]; then
  echo "Cloning ctfd-team-token-plugin ..."
  mkdir -p "$INTEGRATION_DIR/vendor"
  git clone --depth 1 --branch dev https://github.com/NUSGreyhats/ctfd-team-token-plugin.git "$VENDOR_DIR"
fi

echo "Starting CTFd stack ..."
$COMPOSE up -d ctfd-db ctfd-cache ctfd

echo "Starting challenge backend + Postgres ..."
$COMPOSE up -d --build db backend

CTFD_PORT=$($COMPOSE_PORT -- ctfd 8000)
BACKEND_PORT=$($COMPOSE_PORT -- backend 8000)
CTFD_URL="http://127.0.0.1:${CTFD_PORT}"
CHALLENGE_URL="http://127.0.0.1:${BACKEND_PORT}"

echo "Installing integration script dependencies ..."
python3 -m pip install -q -r "$ROOT/scripts/integration/requirements.txt"

echo "Seeding CTFd ..."
CTFD_URL="$CTFD_URL" \
CHALLENGE_URL="$CHALLENGE_URL" \
ENV_OUTPUT="$INTEGRATION_DIR/.env.integration" \
python3 "$ROOT/scripts/integration/seed_ctfd.py"

echo
echo "Integration stack is ready."
echo "  CTFd:     $CTFD_URL  (admin / Password123!)"
echo "  Backend:  $CHALLENGE_URL"
echo "  Test users: alpha / beta (Password123!)"
echo
echo "Run two-team RLS test:"
echo "  make integration-test"
echo
