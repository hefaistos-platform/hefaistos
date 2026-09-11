# HEFAISTOS Installation Manual (SHARP)

This manual is the operator-oriented installation guide for SHARP branch deployments.

## 1. Scope and Assumptions

- This guide is for clean SHARP deployments.
- No in-place data migration is expected.
- Destructive volume reset (`docker compose down -v`) is accepted.

## 2. SHARP Version Baseline

These are the pinned SHARP infrastructure/runtime targets:

| Component | Pinned version |
|---|---|
| Python | 3.12 |
| Django | 6.0.5 |
| Node.js | 24 LTS |
| npm | 11.17.0 |
| React | 19.2.0 |
| PostgreSQL | 18.4 |
| RabbitMQ | 4.3.2-management |
| Elasticsearch | 9.3.6 |
| NGINX | 1.28.0-alpine |

## 3. Prerequisites

- Docker Engine + Docker Compose plugin
- Git
- OpenSSL
- Python 3 (for generating Fernet key)

## 4. Clone and Prepare

```bash
git clone -b main https://github.com/hefaistos-platform/hefaistos.git
cd hefaistos
git pull origin main
cp .env.template .env
cp docker-compose.override.yml.template docker-compose.override.yml
```

If you already cloned the repository earlier, switch to `main` before continuing:

```bash
git checkout main
git pull origin main
```

## 5. Create Secrets

```bash
mkdir -p .secrets
openssl rand -base64 32 > .secrets/db_password
openssl rand -base64 32 > .secrets/rabbitmq_pass
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > .secrets/field_key
echo "your-mailgun-key" > .secrets/mailgun_api
```

Optional (only if using threat intel connector):

```bash
echo "your-misp-api-key" > .secrets/misp_key
```

## 6. Configure `.env`

Set the primary deployment values:

```bash
PUBLIC_BASE_URL=https://your.domain.com
FRONTEND_URL=https://your.domain.com
CORS_ALLOWED_ORIGINS=https://your.domain.com
CSRF_TRUSTED_ORIGINS=https://your.domain.com
SERVER_DOMAIN=your.domain.com
```

## 7. SHARP Clean Bootstrap (Recommended)

Use the scripted bootstrap:

```bash
./scripts/sharp_bootstrap.sh
```

This performs:

1. `docker compose down -v --remove-orphans`
2. `docker compose build --pull`
3. `docker compose --profile workers --profile obs up -d`
4. `docker compose --profile batch run --rm migrate`
5. Search rebuild and smoke checks

Manual equivalent is documented in [scripts/SHARP_BOOTSTRAP_RUNBOOK.md](../scripts/SHARP_BOOTSTRAP_RUNBOOK.md).

Service/profile mapping and startup counts are documented in [compose-service-matrix.md](compose-service-matrix.md).
Rollback path to pre-profile behavior: `docker compose --profile workers --profile obs --profile devtools up -d`.

## 8. Post-Install Initialization

Create the first admin user:

```bash
docker compose exec backend python manage.py createsuperuser
```

Run migrations/seeding as one-shot batch tasks:

```bash
docker compose --profile batch run --rm migrate
docker compose --profile batch run --rm seed
```

Import MITRE ATT&CK:

```bash
docker compose exec backend python manage.py import_mitre_universal --mitre-version 19.0 --mode remote
```

## 9. Access Endpoints

- App UI: `https://your.domain.com`
- GraphQL: `https://your.domain.com/graphql`
- Django admin: `https://your.domain.com/admin`

## 10. AI Model Configuration (Free-Text)

SHARP no longer relies on hardcoded model dropdowns for AI model preference.

- Users can type model names directly in profile settings.
- Admins can type org default models directly in org/system settings.
- Supported style examples:
  - `GPT-5.5`
  - `GEMINI-3.5-FLASH`
  - `CLAUDE-SONNET-4.6`
  - `llama3.1`

Leave model fields empty to allow automatic provider-based model selection.

## 11. Validation Checklist

Use [scripts/SHARP_ACCEPTANCE_REPORT_TEMPLATE.md](../scripts/SHARP_ACCEPTANCE_REPORT_TEMPLATE.md) and verify:

1. GraphQL query/mutation works.
2. JWT login + refresh works.
3. GraphQL file upload works.
4. `/ws/lsp/` websocket handshake works.
5. Elasticsearch indexing/search works.
6. RabbitMQ workers process events.
7. Dark and light themes render correctly on critical pages.

## 12. Troubleshooting: PostgreSQL 18 "unused mount/volume" Error

If `docker compose logs -f db` shows:

- `Error: in 18+, these Docker images are configured ...`
- `Counter to that, there appears to be PostgreSQL data in: /var/lib/postgresql/data (unused mount/volume)`

then old pre-18 volume state is being picked up.

Run:

```bash
docker compose down -v --remove-orphans
docker volume ls | grep postgres_data || true
```

If you still see legacy volumes from old runs (for example `<project>_postgres_data`), remove them:

```bash
docker volume rm <project>_postgres_data
```

Then start again:

```bash
docker compose up -d db
docker compose logs -f db
```

SHARP now mounts PostgreSQL data at `/var/lib/postgresql` (PostgreSQL 18+ recommended layout), not `/var/lib/postgresql/data`.

## 13. Authentication Setup (Entra OIDC + Generic OIDC)

For SHARP authentication architecture and rollout guidance (including break-glass local superuser policy), see:

- [AUTH_SETUP.md](AUTH_SETUP.md)
