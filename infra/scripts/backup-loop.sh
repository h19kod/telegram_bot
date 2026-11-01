#!/bin/sh
# Daily pg_dump (custom format) + media tarball, with retention. Runs inside the backup container.
set -eu
while true; do
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  pg_dump -Fc -f "/backups/db-$ts.dump.tmp" && mv "/backups/db-$ts.dump.tmp" "/backups/db-$ts.dump"
  tar -czf "/backups/media-$ts.tar.gz" -C /media . 2>/dev/null || true
  find /backups -name 'db-*.dump' -mtime "+${BACKUP_KEEP_DAYS}" -delete
  find /backups -name 'media-*.tar.gz' -mtime "+${BACKUP_KEEP_DAYS}" -delete
  echo "backup $ts done"
  sleep 86400
done
