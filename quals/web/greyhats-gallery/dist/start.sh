#!/bin/sh
set -eu

cd "$(dirname "$0")"

docker load < greyhats_gallery_image.tar.gz
docker compose up -d
