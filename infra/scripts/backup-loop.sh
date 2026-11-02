#!/bin/sh
# Runs inside the backup container (see BACKUP_RESTORE.md):
#  - continuous: pg_receivewal streams WAL into /backups/wal through a replication slot (no gaps,
#    flushed per commit) -> point-in-time recovery with RPO of seconds locally;
#  - daily: pg_basebackup (PITR base), pg_dump (portable logical copy), media tarball;
#  - retention: BACKUP_KEEP_DAYS; WAL older than the oldest kept base backup is removed;
#  - self-healing: if the slot is ever invalidated (WAL gap), the archive is set aside, the slot
#    recreated and a new base backup taken at once.
set -eu
SLOT="${BACKUP_SLOT:-sop_backup}"
WAL=/backups/wal
KEEP="${BACKUP_KEEP_DAYS:-14}"
NEED_BASE=/backups/.need-base-backup
mkdir -p "$WAL"

slot_problem() {
  psql -XtAc "select invalidation_reason from pg_replication_slots where slot_name = '$SLOT'" 2>/dev/null
}

ensure_slot() {
  bad=$(slot_problem) || return 1
  if [ -n "$bad" ]; then
    gap="$WAL-gap-$(date -u +%Y%m%dT%H%M%SZ)"
    echo "ERROR: slot $SLOT invalidated ($bad); WAL archive moved to $gap, new base backup follows" >&2
    psql -Xqc "select pg_drop_replication_slot('$SLOT')" >/dev/null || return 1
    mv "$WAL" "$gap" && mkdir -p "$WAL"
    touch "$NEED_BASE"
  fi
  # Reserve WAL at creation: pg_receivewal --create-slot does not, so a checkpoint before the first
  # stream could recycle its start segment and invalidate the slot at once.
  psql -XqAc "select pg_create_physical_replication_slot('$SLOT', true)
    where not exists (select 1 from pg_replication_slots where slot_name = '$SLOT')" >/dev/null
}

stream_wal() {
  while true; do
    if ensure_slot; then
      pg_receivewal -D "$WAL" --slot="$SLOT" --synchronous --no-loop || true
      echo "pg_receivewal stopped; restarting in 5s" >&2
    fi
    sleep 5
  done
}

prune() {
  find /backups -maxdepth 1 -name 'db-*.dump' -mtime "+$KEEP" -delete
  find /backups -maxdepth 1 -name 'media-*.tar.gz' -mtime "+$KEEP" -delete
  find /backups -maxdepth 1 \( -name 'base-*' -o -name 'wal-gap-*' -o -name 'wal-before-pitr-*' \) \
    -type d -mtime "+$KEEP" -exec rm -rf {} +
  oldest=$(find /backups -maxdepth 1 -name 'base-2*' -type d | sort | head -n 1)
  [ -n "$oldest" ] || return 0
  start=$(tar -xzOf "$oldest/base.tar.gz" backup_label | sed -n 's/^START WAL LOCATION: .*(file \(.*\))$/\1/p')
  if [ -n "$start" ]; then pg_archivecleanup "$WAL" "$start"; fi
}

backup_now() {
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  rm -f "$NEED_BASE"
  pg_basebackup -D "/backups/base-$ts.tmp" -Ft -z -X stream -c fast \
    && mv "/backups/base-$ts.tmp" "/backups/base-$ts"
  pg_dump -Fc -f "/backups/db-$ts.dump.tmp" && mv "/backups/db-$ts.dump.tmp" "/backups/db-$ts.dump"
  tar -czf "/backups/media-$ts.tar.gz" -C /media . 2>/dev/null || true
  prune
  echo "backup $ts done"
}

until ensure_slot; do sleep 5; done
stream_wal &
trap 'kill 0' INT TERM

last=0
while true; do
  # A slot invalidated while streaming keeps the connection but no longer reserves WAL.
  if [ -n "$(slot_problem || true)" ]; then pkill -x pg_receivewal || true; fi
  now=$(date +%s)
  if [ $((now - last)) -ge 86400 ] || [ -f "$NEED_BASE" ]; then
    backup_now
    last=$now
  fi
  sleep 60 &
  wait $!
done
