#!/bin/sh
set -eu

# Capture the full flag and drop it from the env immediately.
final_flag="${FLAG:-}"
unset FLAG

random_hex() {
  tr -dc 'a-f0-9' < /dev/urandom | head -c 20
}

install_flag() {
  [ -n "$final_flag" ] || return 0

  while :; do
    flag_path="/flag-$(random_hex).txt"
    [ -e "$flag_path" ] || break
  done

  printf '%s\n' "$final_flag" > "$flag_path"
  chown root:root /
  chmod go-w /
  chown root:root "$flag_path"
  chmod 0444 "$flag_path"
}

if [ "$(id -u)" = "0" ]; then
  install_flag
fi

if [ "$(id -u)" = "0" ] && id appuser >/dev/null 2>&1; then
  exec su-exec appuser "$@"
fi

exec "$@"
