#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "ERROR: docker compose (or docker-compose) is required." >&2
  exit 1
fi

RUN_DESTRUCTIVE=1
SKIP_BUILD=0
SKIP_INDEX_REBUILD=0
YES=0

usage() {
  cat <<'EOF'
Usage: scripts/sharp_bootstrap.sh [options]

Performs the SHARP clean bootstrap flow:
1) docker compose down -v
2) rebuild images
3) start core + workers + obs profiles
4) run Django migrations (one-shot batch service)
5) rebuild Elasticsearch index
6) run smoke checks

Options:
  --no-down-v            Skip destructive `down -v`
  --skip-build           Skip image rebuild
  --skip-index-rebuild   Skip Django search index rebuild
  --yes                  Non-interactive (auto-confirm destructive step)
  -h, --help             Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-down-v)
      RUN_DESTRUCTIVE=0
      shift
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --skip-index-rebuild)
      SKIP_INDEX_REBUILD=1
      shift
      ;;
    --yes)
      YES=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

step() {
  echo
  echo "==> $*"
}

run_compose() {
  "${COMPOSE_CMD[@]}" "$@"
}

confirm_destructive() {
  if [[ "${RUN_DESTRUCTIVE}" -eq 0 ]]; then
    return
  fi

  cat <<'EOF'
WARNING: This will run `docker compose down -v` and permanently delete local volumes.
No data migration path is included in this flow.
EOF

  if [[ "${YES}" -eq 1 ]]; then
    return
  fi

  read -r -p "Continue? [y/N]: " answer
  if [[ "${answer}" != "y" && "${answer}" != "Y" ]]; then
    echo "Aborted."
    exit 1
  fi
}

smoke_check() {
  step "Smoke: GraphQL __typename"
  run_compose exec -T backend curl -fsS \
    -H 'Content-Type: application/json' \
    -d '{"query":"{__typename}"}' \
    http://localhost:8000/graphql >/dev/null
  echo "PASS: GraphQL endpoint reachable."

  step "Smoke: RabbitMQ ping"
  run_compose exec -T rabbitmq rabbitmq-diagnostics -q ping >/dev/null
  echo "PASS: RabbitMQ healthy."

  step "Smoke: Elasticsearch ping"
  run_compose exec -T elasticsearch curl -fsS http://localhost:9200 >/dev/null
  echo "PASS: Elasticsearch reachable."

  step "Smoke: Worker containers running"
  run_compose ps listener ai_generation_worker opentide_enrichment_worker mve_validation_worker
}

confirm_destructive

if [[ "${RUN_DESTRUCTIVE}" -eq 1 ]]; then
  step "Stopping stack and removing volumes"
  run_compose down -v --remove-orphans
fi

if [[ "${SKIP_BUILD}" -eq 0 ]]; then
  step "Rebuilding images"
  run_compose build --pull
fi

step "Starting stack (core + workers + obs)"
run_compose --profile workers --profile obs up -d

step "Running database migrations"
run_compose --profile batch run --rm migrate

if [[ "${SKIP_INDEX_REBUILD}" -eq 0 ]]; then
  step "Rebuilding Elasticsearch index"
  run_compose exec -T backend python manage.py search_index --rebuild -f
fi

step "Refreshing ATT&CK Navigator config/index from local bundles"
run_compose exec -T backend python manage.py sync_navigator_config || true

smoke_check

cat <<'EOF'

SHARP bootstrap completed.
Manual validation checklist:
  - GraphQL query + mutation success
  - JWT login + refresh flow
  - GraphQL file upload path
  - LSP WebSocket flow via /ws/lsp/
  - End-to-end worker queue behavior
See scripts/SHARP_BOOTSTRAP_RUNBOOK.md and scripts/SHARP_ACCEPTANCE_REPORT_TEMPLATE.md.
EOF
