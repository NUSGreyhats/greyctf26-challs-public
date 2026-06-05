#!/bin/sh
set -eu

interval="${RESET_INTERVAL_SECONDS:-300}"

case "$interval" in
  ''|*[!0-9]*)
    echo "RESET_INTERVAL_SECONDS must be a positive integer" >&2
    exit 1
    ;;
esac

if [ "$interval" -le 0 ]; then
  echo "RESET_INTERVAL_SECONDS must be greater than 0" >&2
  exit 1
fi

echo "auto-reset enabled; resetting database every ${interval}s"

echo "applying database state on startup"
/bin/sh /reset/reset-db.sh

while true; do
  sleep "$interval"
  echo "resetting database state"
  /bin/sh /reset/reset-db.sh
done
