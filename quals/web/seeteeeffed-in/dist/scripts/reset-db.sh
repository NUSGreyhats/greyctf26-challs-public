#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 -f /reset/init.sql
