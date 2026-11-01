# Backup & Restore

## What is backed up

| Data | How | Where |
|---|---|---|
| PostgreSQL (everything: tenants, orders, users, encrypted bot tokens) | `backup` service: daily `pg_dump -Fc` | `./backups/db-<UTC>.dump` |
| Media (logos, product images) | same service: daily tar | `./backups/media-<UTC>.tar.gz` |
| `.env` and especially `FIELD_ENCRYPTION_KEYS` | **manually**, once and on every change | password manager / offline |

Retention is `BACKUP_KEEP_DAYS` (default 14). Redis holds only transient data (cache, carts in
progress live in PostgreSQL) and is not backed up.

## Off-site copy (required)

Local backups do not survive losing the server. Sync `./backups` daily to another location, e.g.
with `rclone` to any S3-compatible bucket, encrypted:

```bash
sudo dnf install -y rclone
rclone config   # create an S3 remote named "offsite" and a "crypt" remote on top of it
crontab -e
# 30 3 * * * rclone sync /srv/sop/backups offsite-crypt:sop-backups --max-age 15d
```

For tighter RPO than 24 h (target ≤ 15 min, NFR-6), add WAL archiving with `wal-g`/`pgBackRest`
to the same bucket — planned upgrade; documented in 10-DEPLOYMENT.md.

## Manual backup now

```bash
docker compose exec backup sh -c 'pg_dump -Fc -f /backups/db-manual-$(date -u +%Y%m%dT%H%M%SZ).dump'
```

## Restore (destructive — replaces current data)

```bash
cd /srv/sop
COMPOSE="docker compose" infra/scripts/restore.sh backups/db-20261101T030000Z.dump
```

The script stops the app services, recreates the database, restores the dump, runs the release
job (migrations + reference data) and starts the services again. Restore media with:

```bash
docker run --rm -v sop_media:/media -v "$PWD/backups":/b docker.io/library/alpine \
  sh -c 'tar -xzf /b/media-20261101T030000Z.tar.gz -C /media'
```

## Monthly restore drill

1. Copy the latest dump to a staging machine.
2. Run the restore there; open the dashboard; confirm orders and products are present and a bot
   token still works (proves `FIELD_ENCRYPTION_KEYS` was backed up).
3. Record the date and duration (RTO target ≤ 2 h).
