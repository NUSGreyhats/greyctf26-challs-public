#!/bin/sh
set -eu

# Capture the full flag and drop it from the env immediately.
final_flag="${FLAG:-}"
unset FLAG

install_flag() {
  [ -n "$final_flag" ] || return 0

  if [ -f /app/secrets.js ] && grep -q "grey{placeholder}" /app/secrets.js; then
    sed -i "s|grey{placeholder}|${final_flag}|" /app/secrets.js
  fi
}

if [ "$(id -u)" = "0" ]; then
  install_flag
fi

if [ "$(id -u)" = "0" ] && id appuser >/dev/null 2>&1; then
  exec gosu appuser "$@"
fi

exec "$@"
