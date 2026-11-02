# Backup & Restore

## What is backed up

| Data | How | Where |
|---|---|---|
| PostgreSQL — continuous | `backup` service: `pg_receivewal` streams WAL through the replication slot `sop_backup`, flushed per commit | `./backups/wal/` |
| PostgreSQL — daily base | `pg_basebackup` (tar, gzip, WAL included) — the starting point for point-in-time recovery | `./backups/base-<UTC>/` |
| PostgreSQL — daily logical | `pg_dump -Fc` (portable: other servers/versions, single-table restores) | `./backups/db-<UTC>.dump` |
| Media (logos, product images) | daily tar | `./backups/media-<UTC>.tar.gz` |
| `.env` and especially `FIELD_ENCRYPTION_KEYS` | **manually**, once and on every change | password manager / offline |

Retention is `BACKUP_KEEP_DAYS` (default 14) for base backups, dumps and media; WAL older than
the oldest kept base backup is removed (`pg_archivecleanup`). Redis holds only transient data
(cache, carts in progress live in PostgreSQL) and is not backed up.

**RPO:** seconds on this server (the stream is flushed per commit); off-site it equals the sync
interval below (5 min → meets NFR-6, ≤ 15 min). **RTO:** minutes — the drill restore took 28 s on
a small database; budget roughly the time to unpack the base backup plus replaying one day of WAL.

The WAL stream is protected against gaps: the slot reserves WAL on the server (up to
`PG_MAX_SLOT_WAL_KEEP`, default 8 GB, if the backup service is down). The service checks the slot
every minute; if it is ever invalidated, the log shows `ERROR: slot sop_backup invalidated`, the
old archive is moved to `wal-gap-<UTC>/` (still valid for restores up to the gap) and a new base
backup is taken at once.

## Off-site copy (required)

Local backups do not survive losing the server. Sync `./backups` to another location every five
minutes, e.g. with `rclone` to any S3-compatible bucket, encrypted. The files are owned by root
(written by the container), so use root's crontab:

```bash
sudo dnf install -y rclone
sudo rclone config   # create an S3 remote named "offsite" and a "crypt" remote on top of it
sudo crontab -e
# */5 * * * * flock -n /run/sop-offsite.lock rclone sync /srv/sop/backups offsite-crypt:sop-backups
```

## Manual backup now

```bash
docker compose exec backup sh -c 'pg_dump -Fc -f /backups/db-manual-$(date -u +%Y%m%dT%H%M%SZ).dump'
docker compose exec backup sh -c 'touch /backups/.need-base-backup'   # base backup within a minute
```

## Point-in-time recovery (destructive — replaces current data)

Use this after an accident (wrong bulk delete, bad migration, dropped table): pick the newest
base backup **older** than the moment you want, and a target time just before the accident.

```bash
cd /srv/sop
docker compose exec postgres date -u      # times are compared in the server's clock
COMPOSE="docker compose" infra/scripts/restore-pitr.sh backups/base-20261102T030000Z "2026-11-02 14:29:00+03"
```

Without the second argument it replays all archived WAL (latest state — e.g. after losing the
data volume). The script stops the app and backup services, replaces the data directory with the
base backup, replays WAL up to the target, promotes the server (new timeline), removes the
recovery settings, moves the old archive aside to `wal-before-pitr-<UTC>/`, runs the release job
and starts everything again; the backup service immediately takes a fresh base backup.

To recover after the server itself is lost: copy the off-site `backups/` back to `/srv/sop`,
start `postgres` once with `docker compose up -d postgres`, then run the command above.

## Restore a logical dump (destructive)

```bash
COMPOSE="docker compose" infra/scripts/restore.sh backups/db-20261101T030000Z.dump
```

The script stops the app services, recreates the database, restores the dump, runs the release
job (migrations + reference data) and starts the services again. Restore media with:

```bash
docker run --rm -v sop_media:/media -v "$PWD/backups":/b docker.io/library/alpine \
  sh -c 'tar -xzf /b/media-20261101T030000Z.tar.gz -C /media'
```

## Upgrading an existing installation

The WAL stream needs the replication line in `infra/postgres/pg_hba.conf`, which is applied with
`hba_file`. After pulling this version run `docker compose up -d postgres backup` (recreates both;
the data volume is untouched). Check with
`docker compose logs backup | tail` — a `backup <ts> done` line and files in `backups/wal/`.

## Monthly restore drill

1. Copy the latest base backup and `wal/` to a staging machine.
2. Run `restore-pitr.sh` there, once to a time an hour ago and once without a target; open the
   dashboard; confirm orders and products are present and a bot token still works (proves
   `FIELD_ENCRYPTION_KEYS` was backed up).
3. Record the date and duration (RTO target ≤ 2 h). Last drill: 12-QA-REPORT §5.
