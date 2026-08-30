#!/bin/sh
set -e

# create_schema.sql uses relative includes (\i fnc/..., ccadb/..., etc.),
# so we must run psql from /opt/certwatch.
cd /opt/certwatch

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -f sql/create_schema.sql