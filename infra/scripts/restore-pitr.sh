#!/bin/sh
# Point-in-time recovery from a base backup + the streamed WAL archive (see BACKUP_RESTORE.md).
# Usage: infra/scripts/restore-pitr.sh backups/base-YYYYmmddTHHMMSSZ ["2026-11-02 14:30:00+03"]
# Without a target time it replays all archived WAL (latest state). DESTRUCTIVE: replaces the
# current database. Run from the project root.
set -eu
BASE="${1:?usage: restore-pitr.sh backups/base-<ts> [target-time]}"
TARGET="${2:-}"
BASE_NAME=$(basename "$BASE")
[ -f "backups/$BASE_NAME/base.tar.gz" ] || { echo "no base backup at backups/$BASE_NAME"; exit 1; }
COMPOSE="${COMPOSE:-docker compose}"
APP="api worker beat bot"
ts=$(date -u +%Y%m%dT%H%M%SZ)

$COMPOSE stop $APP backup postgres

# Replace the data directory with the base backup and stage the archived WAL for replay.
$COMPOSE run --rm --no-deps -T -e BASE_NAME="$BASE_NAME" -e TARGET="$TARGET" \
  -v "$PWD/backups:/backups:ro,z" --entrypoint sh postgres -c '
set -eu
D=/var/lib/postgresql/data
find "$D" -mindepth 1 -delete
tar -xzf "/backups/$BASE_NAME/base.tar.gz" -C "$D"
tar -xzf "/backups/$BASE_NAME/pg_wal.tar.gz" -C "$D/pg_wal"
mkdir "$D/restore_wal"
for f in /backups/wal/*; do
  [ -f "$f" ] && cp "$f" "$D/restore_wal/$(basename "$f" .partial)"
done
{
  echo "restore_command = '\''cp $D/restore_wal/%f %p'\''"
  echo "recovery_target_action = '\''promote'\''"
  [ -z "$TARGET" ] || echo "recovery_target_time = '\''$TARGET'\''"
} >> "$D/postgresql.auto.conf"
touch "$D/recovery.signal"
chown -R postgres:postgres "$D"
chmod 700 "$D"
'

$COMPOSE up -d postgres
i=0
until [ "$($COMPOSE exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select pg_is_in_recovery()"' 2>/dev/null | tr -d '[:space:]')" = f ]; do
  i=$((i + 1))
  [ "$i" -le 360 ] || { echo "recovery did not finish; check: $COMPOSE logs postgres"; exit 1; }
  sleep 5
done

# Drop the recovery settings and the staged WAL; the server is now on a new timeline.
$COMPOSE exec -T postgres sh -c '
psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q \
  -c "ALTER SYSTEM RESET restore_command" -c "ALTER SYSTEM RESET recovery_target_action" \
  -c "ALTER SYSTEM RESET recovery_target_time" -c "SELECT pg_reload_conf()" >/dev/null
rm -rf /var/lib/postgresql/data/restore_wal'

# Keep the old WAL archive (other timeline) aside; the backup service starts a fresh stream and
# takes a new base backup as soon as it starts.
$COMPOSE run --rm --no-deps -T --entrypoint sh backup -c "mv /backups/wal /backups/wal-before-pitr-$ts"

$COMPOSE --profile release run --rm release
$COMPOSE start $APP
$COMPOSE up -d backup
echo "restored $BASE_NAME${TARGET:+ to $TARGET}"
