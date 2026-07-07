#!/bin/bash
set -e

echo "[1/3] Building from source"
docker build --target=builder -t greyhats-link-builder . 2>&1 | tail -3

echo "[2/3] Extracting compiled binaries"
CONTAINER=$(docker create greyhats-link-builder true)
for dir in service dist; do
    docker cp "$CONTAINER:/build/index.cgi" "$dir/index.cgi"
    docker cp "$CONTAINER:/opt/custom-lua/bin/lua-custom" "$dir/lua"
done
docker rm "$CONTAINER" > /dev/null

echo "[3/3] Done"
ls -lh service/index.cgi service/lua dist/index.cgi dist/lua
