# SHARP Bootstrap Runbook (Clean Start)

This runbook mirrors `scripts/sharp_bootstrap.sh` for operator-friendly manual execution.

## Critical Warning

`docker compose down -v` **permanently removes local Docker volumes** (database, queues, search data, media, etc.).

This is intentional for SHARP because no in-place data migration is planned.

PostgreSQL 18+ note: data is mounted at `/var/lib/postgresql` (parent path), not `/var/lib/postgresql/data`.
If you hit `unused mount/volume` DB startup errors, remove legacy `<project>_postgres_data` volumes before retrying.

## 1. Stop and Reset Runtime State

```bash
docker compose down -v --remove-orphans
```

## 2. Rebuild with SHARP Pins

```bash
docker compose build --pull
```

## 3. Start Services

```bash
docker compose --profile workers --profile obs up -d
docker compose ps
```

## 4. Django Bootstrap

```bash
docker compose --profile batch run --rm migrate
```

## 5. Search + Navigator Rebuild

```bash
docker compose exec backend python manage.py search_index --rebuild -f
docker compose exec backend python manage.py sync_navigator_config
```

## 6. Smoke Checks

### GraphQL Reachability

```bash
docker compose exec backend curl -fsS \
  -H 'Content-Type: application/json' \
  -d '{"query":"{__typename}"}' \
  http://localhost:8000/graphql
```

### RabbitMQ Health

```bash
docker compose exec rabbitmq rabbitmq-diagnostics -q ping
```

### Elasticsearch Health

```bash
docker compose exec elasticsearch curl -fsS http://localhost:9200
```

### Worker Containers

```bash
docker compose ps listener ai_generation_worker opentide_enrichment_worker mve_validation_worker
```

## 7. Manual End-to-End Validation

1. GraphQL authenticated query and mutation.
2. JWT login and refresh (`/api/token`, `/api/token/refresh`).
3. GraphQL file upload flow.
4. LSP WebSocket handshake + message flow through `/ws/lsp/`.
5. Elasticsearch index + retrieval in app UI.
6. RabbitMQ listener and async worker processing.
7. Dark mode visual pass on critical routes:
   `Lifecycle Hub`, `Coverage Map`, `Rule Detail`, detection editor modal.

## Optional Automation

Use the scripted equivalent:

```bash
./scripts/sharp_bootstrap.sh
```
