#!/usr/bin/env bash
# Print the host port mapped to a Compose service container port.
# Usage: compose-port.sh <compose-args...> -- <service> <container-port>
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: compose-port.sh <compose-args...> -- <service> <container-port>" >&2
  exit 1
fi

args=()
while [[ $# -gt 0 && "$1" != "--" ]]; do
  args+=("$1")
  shift
done
shift

service=$1
container_port=$2

hostport=$(docker compose "${args[@]}" port "$service" "$container_port")
echo "${hostport##*:}"
