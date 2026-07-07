#!/bin/sh
set -eu
flag="${FLAG:-}"
[ -z "$flag" ] && flag="grey{missing_flag}"
printf '%s' "$flag" > /flag.txt
chmod 444 /flag.txt
exec lighttpd -D -f /etc/lighttpd/lighttpd.conf
