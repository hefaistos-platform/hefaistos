# HEFAISTOS Backup Guide (Local/External Media)

## Overview

`backup-hefaistos.sh` creates local compressed backups of your current HEFAISTOS runtime state.

Supported destination types:
- Local disk (`./backups` by default)
- Externally mounted media (USB/NAS mount path), provided by system administrator

Out of scope by design:
- Remote copy/upload logic in the script
- Elasticsearch snapshot export/restore

## What Gets Backed Up

Each archive includes:
- PostgreSQL dump from the running `db` container
- Media volume data from `/app/media`
- ATT&CK navigator data volume from `/navigator-data`
- Repository `.secrets` folder and connector token (if present)
- Key config files (`.env`, compose files, nginx config/certs, backend deployment settings)
- Metadata (`compose ps`, compose version, git commit where available)
- SHA-256 checksum file (`.sha256`) when checksum tools are available

## Prerequisites

- Docker + Docker Compose (`docker compose` or `docker-compose`)
- Running `db` and `backend` containers for backup
- `tar` and `gzip`

## Backup Usage

### 1. Default local backup

```bash
./scripts/backup-hefaistos.sh
```

### 2. Backup to external mounted media

```bash
./scripts/backup-hefaistos.sh --backup-dir /mnt/backup-drive/hefaistos
```

### 3. Custom retention

```bash
./scripts/backup-hefaistos.sh --retention-days 14
```

### 4. Legacy positional form (still supported)

```bash
./scripts/backup-hefaistos.sh /mnt/backup-drive/hefaistos 14
```

## Restore Usage

Restore overwrites database and runtime volume data (`media`, `navigator-data`) and may replace `.secrets`.

### 1. Restore from archive

```bash
./scripts/backup-hefaistos.sh --restore /path/to/hefaistos-backup-YYYYmmdd_HHMMSS.tar.gz
```

### 2. Non-interactive restore

```bash
./scripts/backup-hefaistos.sh --restore /path/to/hefaistos-backup-YYYYmmdd_HHMMSS.tar.gz --yes
```

During restore:
- `db` and `backend` are started if needed
- Database is restored from SQL dump
- `media` and `navigator-data` are replaced with backup content
- `.secrets` is restored if present in archive (current `.secrets` is preserved as `.secrets.pre_restore_<timestamp>`)
- Archived config bundle is staged under `.restore/config-<timestamp>` for manual review

## Elasticsearch Note

Elasticsearch snapshot handling was intentionally removed from this script.

After restore, if search index state is inconsistent, rebuild from app data:

```bash
docker compose exec backend python manage.py search_index --rebuild -f
```

## Suggested Cron Setup

Example: run backup daily at 02:00 to externally mounted path.

```bash
crontab -e

0 2 * * * /opt/HEFAISTOS-Lemnian/scripts/backup-hefaistos.sh --backup-dir /mnt/backup-drive/hefaistos --retention-days 30 >> /var/log/hefaistos-backup.log 2>&1
```

## Verify Backups

```bash
# List archives
ls -lh /path/to/backup-dir/hefaistos-backup-*.tar.gz

# Verify checksum (Linux)
cd /path/to/backup-dir
sha256sum -c hefaistos-backup-YYYYmmdd_HHMMSS.tar.gz.sha256

# Verify checksum (macOS)
cd /path/to/backup-dir
shasum -a 256 -c hefaistos-backup-YYYYmmdd_HHMMSS.tar.gz.sha256
```

## Troubleshooting

### Database container is not running

```bash
docker compose up -d db backend
```

### Restore says checksum file missing

The `.sha256` file is optional. Restore will continue with a warning.

### Permission denied on backup destination

Ensure target path is mounted and writable by the user running cron/script.
