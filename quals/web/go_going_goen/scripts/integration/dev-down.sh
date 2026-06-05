#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE="docker compose -p g26-q-integration -f $ROOT/dev/integration/docker-compose.test.yml"

$COMPOSE down -v --remove-orphans
