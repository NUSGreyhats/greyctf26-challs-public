#!/bin/sh
set -eu

SOURCE_IMAGE="${1:-baby-web-photos}"
TARGET_IMAGE="${2:-$SOURCE_IMAGE}"
CONTAINER_NAME="greyhats-post-build-$$"
TMP_DIR="$(mktemp -d)"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT INT TERM

docker run -d --name "$CONTAINER_NAME" --user root --entrypoint sleep "$SOURCE_IMAGE" infinity >/dev/null

docker cp "$CONTAINER_NAME:/app/node_modules/ejs/lib/ejs.js" "$TMP_DIR/ejs.js"
node "$(dirname "$0")/patch-ejs-whitelist.js" "$TMP_DIR/ejs.js"
docker cp "$TMP_DIR/ejs.js" "$CONTAINER_NAME:/app/node_modules/ejs/lib/ejs.js"

docker exec "$CONTAINER_NAME" sh -eu -c '
  mkdir -p /app/uploads
  if ! id appuser >/dev/null 2>&1; then
    useradd --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin appuser
  fi

  chown -R root:root /app
  chown -R appuser:appuser /app/uploads
  chown root:appuser /app/views

  chmod -R 755 /app
  chmod -R 775 /app/uploads
  chmod 1775 /app/views
  chmod 644 /app/views/*.ejs

  chmod 555 /tmp /var/tmp
  if [ -d /run/lock ]; then
    chmod 555 /run/lock
  fi

  find / -xdev -type f -perm /6000 -exec chmod a-s {} + || true
'

docker commit \
  --change 'ENTRYPOINT ["/usr/local/bin/install-flag.sh"]' \
  --change 'CMD ["node","src/server.js"]' \
  --change "USER root" \
  --change "ENV NODE_ENV=production" \
  --change "ENV HOME=/nonexistent" \
  "$CONTAINER_NAME" "$TARGET_IMAGE" >/dev/null

echo "Patched $SOURCE_IMAGE -> $TARGET_IMAGE"
