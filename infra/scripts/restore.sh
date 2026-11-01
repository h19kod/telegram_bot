#!/bin/sh
# Usage: infra/scripts/restore.sh backups/db-YYYYmmddTHHMMSSZ.dump
# Restores into the running postgres service. DESTRUCTIVE: replaces current data.
set -eu
DUMP="$1"
[ -f "$DUMP" ] || { echo "no such file: $DUMP"; exit 1; }
COMPOSE="${COMPOSE:-docker compose}"
$COMPOSE stop api worker beat bot
$COMPOSE exec -T postgres sh -c 'dropdb --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
$COMPOSE exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' < "$DUMP"
$COMPOSE --profile release run --rm release
$COMPOSE start api worker beat bot
echo "restored $DUMP"
