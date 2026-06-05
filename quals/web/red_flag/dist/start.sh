#!/bin/sh
set -eu

cd "$(dirname "$0")"

docker load < red_flag_image.tar.gz
docker compose up -d
