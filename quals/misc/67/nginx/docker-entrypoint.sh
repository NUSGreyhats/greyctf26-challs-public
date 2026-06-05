#!/bin/sh
set -eu

# Log under /tmp so nginx still works after we drop from root -> uid 101. Symlinks to
# /dev/stderr only work when the container starts as 101, not after su/su-exec.
mkdir -p /tmp/nginx-logs /var/cache/nginx
chown 101:101 /tmp/nginx-logs /var/cache/nginx
: > /tmp/nginx-logs/error.log
: > /tmp/nginx-logs/access.log
chown 101:101 /tmp/nginx-logs/error.log /tmp/nginx-logs/access.log
chmod 644 /tmp/nginx-logs/error.log /tmp/nginx-logs/access.log
# Stream logs to docker (tail in background, replaced each start)
tail -F /tmp/nginx-logs/error.log >&2 &
tail -F /tmp/nginx-logs/access.log >&1 &

# Host Let's Encrypt keys are usually root-only.
# Copy certs into a container path owned by nginx so we keep a non-root runtime.
domain="${CERTBOT_DOMAIN:-${SERVER_NAME:-}}"
le_dir="/etc/letsencrypt/live/${domain}"
cert_dir="/tmp/nginx-certs"

if [ -n "${domain}" ] && [ -r "${le_dir}/fullchain.pem" ] && [ -r "${le_dir}/privkey.pem" ]; then
  mkdir -p "${cert_dir}"
  cp -fL "${le_dir}/fullchain.pem" "${cert_dir}/fullchain.pem"
  cp -fL "${le_dir}/privkey.pem" "${cert_dir}/privkey.pem"
  chown -R 101:101 "${cert_dir}"
  chmod 0750 "${cert_dir}"
  chmod 0640 "${cert_dir}"/*.pem
  export SSL_CERTIFICATE="${cert_dir}/fullchain.pem"
  export SSL_CERTIFICATE_KEY="${cert_dir}/privkey.pem"
else
  export SSL_CERTIFICATE="${SSL_CERTIFICATE:-${le_dir}/fullchain.pem}"
  export SSL_CERTIFICATE_KEY="${SSL_CERTIFICATE_KEY:-${le_dir}/privkey.pem}"
fi

export DOLLAR="${DOLLAR:-\$}"

# Do not exec su-exec: keep this shell as pid 1 so log tail processes stay alive.
su-exec 101:101 /docker-entrypoint.sh "$@"
