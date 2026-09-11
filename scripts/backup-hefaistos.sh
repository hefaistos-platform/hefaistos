#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
DEFAULT_BACKUP_DIR="${REPO_ROOT}/backups"
DEFAULT_RETENTION_DAYS=30
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

MODE="backup"
RESTORE_ARCHIVE=""
BACKUP_DIR="$DEFAULT_BACKUP_DIR"
RETENTION_DAYS="$DEFAULT_RETENTION_DAYS"
ASSUME_YES=0

COMPOSE_CMD=()

usage() {
  cat <<'USAGE'
HEFAISTOS backup/restore utility (local storage only)

Usage:
  ./scripts/backup-hefaistos.sh [options]
  ./scripts/backup-hefaistos.sh --restore <archive.tar.gz> [--yes]

Backup options:
  --backup-dir <path>       Backup destination directory (default: ./backups)
  --retention-days <days>   Delete local backups older than N days (default: 30)

Restore options:
  --restore <archive>       Restore from a local backup archive
  --yes                     Skip interactive confirmation prompts

Compatibility (legacy positional args, backup mode only):
  ./scripts/backup-hefaistos.sh [backup_dir] [retention_days]

Notes:
  - This script supports local backups only (including externally mounted media).
  - Elasticsearch snapshots are intentionally not included.
USAGE
}

log() {
  local level="$1"
  shift
  printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$*"
}

fail() {
  log "ERROR" "$*"
  exit 1
}

warn() {
  log "WARN" "$*"
}

info() {
  log "INFO" "$*"
}

confirm_or_exit() {
  local prompt="$1"
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    return 0
  fi

  local answer
  read -r -p "$prompt Type 'yes' to continue: " answer
  if [[ "$answer" != "yes" ]]; then
    fail "Operation aborted by user."
  fi
}

require_command() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: $cmd"
}

resolve_compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
    return 0
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
    return 0
  fi

  fail "Docker Compose command not found (docker compose / docker-compose)."
}

compose() {
  "${COMPOSE_CMD[@]}" "$@"
}

validate_positive_int() {
  local value="$1"
  local label="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || fail "$label must be a positive integer. Got: $value"
  [[ "$value" -gt 0 ]] || fail "$label must be greater than 0."
}

copy_with_structure() {
  local rel_path="$1"
  local src="${REPO_ROOT}/${rel_path}"
  local dst="${BACKUP_WORK_DIR}/config/${rel_path}"

  if [[ -f "$src" ]]; then
    mkdir -p "$(dirname "$dst")"
    cp -p "$src" "$dst"
    return
  fi

  if [[ -d "$src" ]]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
  fi
}

write_checksum() {
  local archive_file="$1"
  local archive_name
  archive_name="$(basename "$archive_file")"
  local checksum_file="${archive_file}.sha256"

  if command -v sha256sum >/dev/null 2>&1; then
    (
      cd "$(dirname "$archive_file")"
      sha256sum "$archive_name" > "${archive_name}.sha256"
    )
    info "Checksum written: $checksum_file"
    return
  fi

  if command -v shasum >/dev/null 2>&1; then
    (
      cd "$(dirname "$archive_file")"
      shasum -a 256 "$archive_name" > "${archive_name}.sha256"
    )
    info "Checksum written: $checksum_file"
    return
  fi

  warn "No sha256 utility found; checksum file was not created."
}

verify_checksum_if_present() {
  local archive_file="$1"
  local checksum_file="${archive_file}.sha256"

  if [[ ! -f "$checksum_file" ]]; then
    warn "Checksum file not found (${checksum_file}); skipping checksum validation."
    return
  fi

  local archive_name
  archive_name="$(basename "$archive_file")"

  if command -v sha256sum >/dev/null 2>&1; then
    (
      cd "$(dirname "$archive_file")"
      sha256sum -c "$(basename "$checksum_file")"
    ) >/dev/null
    info "Checksum verification passed."
    return
  fi

  if command -v shasum >/dev/null 2>&1; then
    (
      cd "$(dirname "$archive_file")"
      shasum -a 256 -c "$(basename "$checksum_file")"
    ) >/dev/null
    info "Checksum verification passed."
    return
  fi

  warn "No sha256 verification utility available; skipped checksum validation."
}

preflight_backup() {
  require_command docker
  require_command tar
  require_command gzip
  resolve_compose_cmd

  cd "$REPO_ROOT"
  [[ -f "docker-compose.yml" ]] || fail "Run from repository context with docker-compose.yml available."

  if ! compose ps --status running db 2>/dev/null | grep -q .; then
    fail "Database container is not running. Start it with: docker compose up -d db"
  fi

  if ! compose ps --status running backend 2>/dev/null | grep -q .; then
    fail "Backend container is not running. Start it with: docker compose up -d backend"
  fi
}

preflight_restore() {
  require_command docker
  require_command tar
  require_command gzip
  resolve_compose_cmd

  cd "$REPO_ROOT"
  [[ -f "docker-compose.yml" ]] || fail "Run from repository context with docker-compose.yml available."
  [[ -n "$RESTORE_ARCHIVE" ]] || fail "--restore requires an archive path."
  [[ -f "$RESTORE_ARCHIVE" ]] || fail "Restore archive not found: $RESTORE_ARCHIVE"
}

wait_for_database() {
  local max_attempts=60
  local attempt=0

  while [[ "$attempt" -lt "$max_attempts" ]]; do
    if compose exec -T db sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 2
  done

  return 1
}

collect_metadata() {
  mkdir -p "${BACKUP_WORK_DIR}/meta"

  {
    echo "timestamp=${TIMESTAMP}"
    echo "repo_root=${REPO_ROOT}"
    echo "hostname=$(hostname 2>/dev/null || echo unknown)"
    echo "uname=$(uname -a 2>/dev/null || echo unknown)"
    if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      echo "git_commit=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
      echo "git_branch=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
    fi
    echo "compose_cmd=${COMPOSE_CMD[*]}"
  } > "${BACKUP_WORK_DIR}/meta/backup_manifest.txt"

  compose version > "${BACKUP_WORK_DIR}/meta/compose_version.txt" 2>&1 || true
  compose ps > "${BACKUP_WORK_DIR}/meta/compose_ps.txt" 2>&1 || true
  compose exec -T db sh -lc 'echo "POSTGRES_DB=$POSTGRES_DB"; echo "POSTGRES_USER=$POSTGRES_USER"' \
    > "${BACKUP_WORK_DIR}/meta/db_runtime_env.txt" 2>&1 || true
}

backup_database() {
  info "Backing up PostgreSQL database..."

  mkdir -p "${BACKUP_WORK_DIR}/db"

  if compose exec -T db sh -lc 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    > "${BACKUP_WORK_DIR}/db/postgres.sql"; then
    if [[ ! -s "${BACKUP_WORK_DIR}/db/postgres.sql" ]]; then
      fail "Database dump completed but output is empty."
    fi
    info "Database backup completed."
  else
    fail "Database dump failed."
  fi
}

backup_media() {
  info "Backing up media volume content (/app/media)..."

  if compose exec -T backend sh -lc 'test -d /app/media' >/dev/null 2>&1; then
    compose exec -T backend tar -C /app -cf - media | tar -C "$BACKUP_WORK_DIR" -xf -
    info "Media backup completed."
  else
    warn "Backend media path not found; skipped media backup."
  fi
}

backup_navigator_data() {
  info "Backing up navigator data volume content (/navigator-data)..."

  if compose exec -T backend sh -lc 'test -d /navigator-data' >/dev/null 2>&1; then
    compose exec -T backend tar -C / -cf - navigator-data | tar -C "$BACKUP_WORK_DIR" -xf -
    info "Navigator data backup completed."
  else
    warn "Navigator data path not found; skipped navigator-data backup."
  fi
}

backup_secrets() {
  info "Backing up .secrets and connector token..."

  mkdir -p "${BACKUP_WORK_DIR}/secrets"

  if [[ -d "${REPO_ROOT}/.secrets" ]]; then
    cp -a "${REPO_ROOT}/.secrets" "${BACKUP_WORK_DIR}/secrets/.secrets"
    info ".secrets backup completed."
  else
    warn "Repository .secrets directory not found; skipped."
  fi

  if compose exec -T backend sh -lc 'test -s /run/connector/token.jwt' >/dev/null 2>&1; then
    compose exec -T backend cat /run/connector/token.jwt > "${BACKUP_WORK_DIR}/secrets/connector-token.jwt"
    info "Connector token backup completed."
  else
    warn "Connector token not present in backend container; skipped."
  fi
}

backup_configuration() {
  info "Backing up configuration files..."

  local paths=(
    ".env"
    ".env.template"
    "docker-compose.yml"
    "docker-compose.override.yml"
    "docker-compose.override.yml.template"
    "backend/hefaistos/settings.py"
    "nginx/conf.d"
    "nginx/certs"
  )

  for path in "${paths[@]}"; do
    copy_with_structure "$path"
  done

  info "Configuration backup completed."
}

create_archive() {
  info "Creating compressed backup archive..."
  tar -C "$BACKUP_DIR" -czf "$ARCHIVE_FILE" "$BACKUP_BASENAME"
  write_checksum "$ARCHIVE_FILE"
  rm -rf "$BACKUP_WORK_DIR"
  info "Archive created: $ARCHIVE_FILE"
}

cleanup_old_backups() {
  info "Applying retention policy (${RETENTION_DAYS} days)..."

  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'hefaistos-backup-*.tar.gz' -mtime "+${RETENTION_DAYS}" -delete || true
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'hefaistos-backup-*.tar.gz.sha256' -mtime "+${RETENTION_DAYS}" -delete || true
  find "$BACKUP_DIR" -maxdepth 1 -type d -name 'hefaistos-backup-*' -mtime "+${RETENTION_DAYS}" -exec rm -rf {} + || true

  info "Retention cleanup completed."
}

run_backup() {
  preflight_backup

  mkdir -p "$BACKUP_DIR"

  BACKUP_BASENAME="hefaistos-backup-${TIMESTAMP}"
  BACKUP_WORK_DIR="${BACKUP_DIR}/${BACKUP_BASENAME}"
  ARCHIVE_FILE="${BACKUP_DIR}/${BACKUP_BASENAME}.tar.gz"

  mkdir -p "$BACKUP_WORK_DIR"

  info "Starting backup"
  info "Backup directory: $BACKUP_DIR"

  collect_metadata
  backup_database
  backup_media
  backup_navigator_data
  backup_secrets
  backup_configuration

  create_archive
  cleanup_old_backups

  info "Backup finished successfully."
  info "Archive: $ARCHIVE_FILE"
  if [[ -f "${ARCHIVE_FILE}.sha256" ]]; then
    info "Checksum: ${ARCHIVE_FILE}.sha256"
  fi
  info "Elasticsearch snapshots are intentionally not included in this backup."
}

restore_database() {
  local extracted_root="$1"
  local db_dump_file="${extracted_root}/db/postgres.sql"
  if [[ ! -f "$db_dump_file" ]]; then
    db_dump_file="${extracted_root}/db/hefaistos_db.sql"
  fi

  [[ -f "$db_dump_file" ]] || fail "Database dump not found in archive: $db_dump_file"

  info "Restoring PostgreSQL database from backup..."
  compose exec -T db sh -lc 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$db_dump_file"
  info "Database restore completed."
}

restore_media() {
  local extracted_root="$1"
  local media_source_dir="${extracted_root}/media"

  if [[ -d "${extracted_root}/media/media" ]]; then
    # Legacy backup format used media/media nesting.
    media_source_dir="${extracted_root}/media/media"
  fi

  if [[ -d "$media_source_dir" ]]; then
    info "Restoring media data to /app/media..."
    compose exec -T backend sh -lc 'mkdir -p /app/media && find /app/media -mindepth 1 -maxdepth 1 -exec rm -rf {} +'
    tar -C "$media_source_dir" -cf - . | compose exec -T backend tar -C /app/media -xf -
    info "Media restore completed."
  else
    warn "No media directory found in archive; skipped media restore."
  fi
}

restore_navigator_data() {
  local extracted_root="$1"

  if [[ -d "${extracted_root}/navigator-data" ]]; then
    info "Restoring navigator data to /navigator-data..."
    compose exec -T backend sh -lc 'mkdir -p /navigator-data && find /navigator-data -mindepth 1 -maxdepth 1 -exec rm -rf {} +'
    tar -C "$extracted_root" -cf - navigator-data | compose exec -T backend tar -C / -xf -
    info "Navigator data restore completed."
  else
    warn "No navigator-data directory found in archive; skipped navigator restore."
  fi
}

restore_secrets() {
  local extracted_root="$1"
  local archived_secrets="${extracted_root}/secrets/.secrets"

  if [[ -d "$archived_secrets" ]]; then
    info "Restoring .secrets directory..."

    if [[ -d "${REPO_ROOT}/.secrets" ]]; then
      local backup_path="${REPO_ROOT}/.secrets.pre_restore_${TIMESTAMP}"
      cp -a "${REPO_ROOT}/.secrets" "$backup_path"
      info "Current .secrets was preserved at: $backup_path"
      rm -rf "${REPO_ROOT}/.secrets"
    fi

    cp -a "$archived_secrets" "${REPO_ROOT}/.secrets"
    chmod 700 "${REPO_ROOT}/.secrets" || true
    info ".secrets restore completed."
  else
    warn "No .secrets payload found in archive; skipped secrets restore."
  fi

  if [[ -f "${extracted_root}/secrets/connector-token.jwt" ]]; then
    info "Restoring connector token to backend runtime volume..."
    compose exec -T backend sh -lc 'mkdir -p /run/connector'
    compose exec -T backend sh -lc 'cat > /run/connector/token.jwt && chmod 600 /run/connector/token.jwt' \
      < "${extracted_root}/secrets/connector-token.jwt"
    info "Connector token restore completed."
  fi
}

stage_config_for_manual_review() {
  local extracted_root="$1"
  local config_src="${extracted_root}/config"

  if [[ -d "$config_src" ]]; then
    local stage_dir="${REPO_ROOT}/.restore/config-${TIMESTAMP}"
    mkdir -p "${REPO_ROOT}/.restore"
    cp -a "$config_src" "$stage_dir"
    info "Configuration files were staged for manual review at: $stage_dir"
  fi
}

run_restore() {
  preflight_restore
  verify_checksum_if_present "$RESTORE_ARCHIVE"

  confirm_or_exit "Restore will overwrite database/media/navigator data and may replace .secrets."

  info "Ensuring required containers are running (db + backend)..."
  compose up -d db backend >/dev/null

  if ! wait_for_database; then
    fail "Database did not become ready in time."
  fi

  local restore_tmp
  restore_tmp="$(mktemp -d "${TMPDIR:-/tmp}/hefaistos-restore-XXXXXX")"

  info "Extracting archive to temporary directory..."
  tar -xzf "$RESTORE_ARCHIVE" -C "$restore_tmp"

  local extracted_root
  extracted_root="$(find "$restore_tmp" -mindepth 1 -maxdepth 1 -type d | head -n1)"
  [[ -n "$extracted_root" ]] || fail "Could not locate extracted backup payload."

  restore_database "$extracted_root"
  restore_media "$extracted_root"
  restore_navigator_data "$extracted_root"
  restore_secrets "$extracted_root"
  stage_config_for_manual_review "$extracted_root"

  rm -rf "$restore_tmp"

  info "Restore completed successfully."
  info "Restarting stack so services pick up restored state..."
  compose up -d >/dev/null
  info "Reminder: Elasticsearch snapshots are not restored by this script."
  info "If needed, rebuild search indexes with: docker compose exec backend python manage.py search_index --rebuild -f"
}

parse_args() {
  local positional=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --backup-dir)
        [[ $# -ge 2 ]] || fail "--backup-dir requires a value."
        BACKUP_DIR="$2"
        shift 2
        ;;
      --retention-days)
        [[ $# -ge 2 ]] || fail "--retention-days requires a value."
        RETENTION_DAYS="$2"
        shift 2
        ;;
      --restore)
        [[ $# -ge 2 ]] || fail "--restore requires an archive path."
        MODE="restore"
        RESTORE_ARCHIVE="$2"
        shift 2
        ;;
      --yes)
        ASSUME_YES=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      --)
        shift
        while [[ $# -gt 0 ]]; do
          positional+=("$1")
          shift
        done
        ;;
      -*)
        fail "Unknown option: $1"
        ;;
      *)
        positional+=("$1")
        shift
        ;;
    esac
  done

  if [[ "$MODE" == "backup" ]]; then
    if [[ ${#positional[@]} -ge 1 ]]; then
      BACKUP_DIR="${positional[0]}"
    fi
    if [[ ${#positional[@]} -ge 2 ]]; then
      RETENTION_DAYS="${positional[1]}"
    fi
    if [[ ${#positional[@]} -gt 2 ]]; then
      fail "Too many positional arguments. Use --help for usage."
    fi
  else
    if [[ ${#positional[@]} -gt 0 ]]; then
      fail "Positional arguments are not supported with --restore mode."
    fi
  fi

  validate_positive_int "$RETENTION_DAYS" "retention-days"

  BACKUP_DIR="$(cd "$REPO_ROOT" && mkdir -p "$BACKUP_DIR" && cd "$BACKUP_DIR" && pwd)"

  if [[ "$MODE" == "restore" ]]; then
    if [[ "$RESTORE_ARCHIVE" != /* ]]; then
      RESTORE_ARCHIVE="$(cd "$REPO_ROOT" && cd "$(dirname "$RESTORE_ARCHIVE")" && pwd)/$(basename "$RESTORE_ARCHIVE")"
    fi
  fi
}

main() {
  parse_args "$@"

  if [[ "$MODE" == "backup" ]]; then
    run_backup
  else
    run_restore
  fi
}

main "$@"
