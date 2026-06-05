#!/bin/sh
set -eu

random_hex() {
  tr -dc 'a-f0-9' < /dev/urandom | head -c 20
}

install_flag() {
  flag_path="/flag-seed.txt"
  if [ ! -f "$flag_path" ]; then
    return 0
  fi

  flag_suffix="${FLAG:-}"
  if [ -n "$flag_suffix" ]; then
    flag_contents="$(cat "$flag_path")"
    printf '%s_%s}\n' "${flag_contents%\}}" "$flag_suffix" > "$flag_path"
  fi

  while :; do
    new_path="/flag-$(random_hex).txt"
    if [ "$new_path" != "$flag_path" ] && [ ! -e "$new_path" ]; then
      break
    fi
  done

  mv "$flag_path" "$new_path"
  chown root:root /
  chmod go-w /
  chown root:root "$new_path"
  chmod 0444 "$new_path"
}

if [ "$(id -u)" = "0" ]; then
  install_flag

  if id appuser >/dev/null 2>&1; then
    exec su-exec appuser "$@"
  fi
fi

exec "$@"
