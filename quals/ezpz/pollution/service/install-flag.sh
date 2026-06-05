#!/bin/sh
set -eu

install_flag() {
  flag_path="/flag-seed.txt"
  if [ ! -f "$flag_path" ]; then
    return 0
  fi

  flag_suffix="${FLAG:-}"
  if [ -n "$flag_suffix" ]; then
    flag_contents="$(cat "$flag_path")"
    final_flag="$(printf '%s_%s}\n' "${flag_contents%\}}" "$flag_suffix")"
    printf final_flag
  fi

  if [ -f /app/secrets.js ] && grep -q "grey{placeholder}" /app/secrets.js; then
    sed -i "s|grey{placeholder}|${final_flag}|" /app/secrets.js
  fi
}

if [ "$(id -u)" = "0" ]; then
  install_flag

  if id appuser >/dev/null 2>&1; then
    exec gosu appuser "$@"
  fi
fi

exec "$@"
