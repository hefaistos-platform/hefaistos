# Hefaistos

<div align="center">

![HEFAISTOS Logo](frontend/public/logo.png)

**Enterprise Detection Engineering & Threat Intelligence Platform**

[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](./LICENSE)
[![Platform Version](https://img.shields.io/badge/platform-1.5.38-0A66C2.svg)](./VERSION) <!-- hefaistos-version-badge -->
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![Django](https://img.shields.io/badge/django-6.0.5-green.svg)](https://djangoproject.com)
[![React](https://img.shields.io/badge/react-19.2-61dafb.svg)](https://reactjs.org)
[![TypeScript](https://img.shields.io/badge/typescript-5+-blue.svg)](https://typescriptlang.org)
[![Docker](https://img.shields.io/badge/docker-compose-2496ed.svg)](https://docker.com)

</div>

> *"What happens when one sleep-deprived human tries to fix security with the 'help' of AI systems that have never actually seen a network packet. Spoiler: surprisingly, it works."*

---

## 🎯 Overview

HEFAISTOS is a comprehensive **Detection Engineering Platform** designed for security operations teams. It provides an end-to-end workflow from threat hypothesis development through detection rule creation, testing, deployment, and MITRE ATT&CK coverage tracking.

### Key Capabilities

- 🔬 **Detection Workbench** - Visual graph-based detection development environment with advanced Capability Abstraction Map (auto-derived from library, layered bands, robustness encoding, gap detection)
- 🤖 **AI-Powered Rule Generation** - Multi-provider AI support (OpenAI, Gemini, Claude)
- 📊 **MITRE ATT&CK Integration** - Full coverage mapping and technique tracking
- 🕵️ **Threat Intelligence** - MISP integration for automated workbench creation
- 🔄 **Git Repository Sync** - Bidirectional KQL/SPL/WAZUH rule synchronization
- 📋 **ACH Analysis** - Structured Analysis of Competing Hypotheses
- 👥 **Collaborative Workflow** - Peer review and approval process
- 🏢 **Multi-Tenancy** - Organization and entity-based isolation (MSSP support)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              NGINX (Reverse Proxy)                      │
│                            Ports: 80 (HTTP) / 443 (HTTPS)               │
└─────────────────────────────────────────────────────────────────────────┘
                    │                                    │
                    ▼                                    ▼
┌─────────────────────────────┐        ┌─────────────────────────────────┐
│         Frontend            │        │           Backend               │
│    React 19 + TypeScript    │        │   Django 6.0 + GraphQL          │
│    TailwindCSS + Ant Design │        │   Gunicorn + WebSocket          │
│    React Flow (Graphs)      │        │   JWT Authentication            │
└─────────────────────────────┘        └─────────────────────────────────┘
                                                        │
                    ┌───────────────────────────────────┼───────────────────┐
                    │                                   │                   │
                    ▼                                   ▼                   ▼
        ┌───────────────────┐            ┌─────────────────────┐    ┌──────────────┐
        │    PostgreSQL     │            │     RabbitMQ        │    │ Elasticsearch│
        │    (Database)     │            │  (Event Messaging)  │    │   (Search)   │
        └───────────────────┘            └─────────────────────┘    └──────────────┘
                                                    ║
                    ┌───────────────────────────────┴───────────────────────────┐
                    │                   Event Connectors                        │
                    ├─────────────┬─────────────┬─────────────┬───────────────-─┤
                    │   Rule      │ Notification│ Threat Intel│   Git Push      │
                    │ Connector   │ Connector   │ Connector   │   Connector     │
                    │ (Git Sync)  │ (Alerts)    │ (MISP)      │ (Export Rules)  │
                    └─────────────┴─────────────┴─────────────┴────────────────-┘
```

---

## ✨ Features

### 🔬 Detection Workbench

The visual workbench provides a complete detection engineering environment:

- **Capability Abstraction Map** - Auto-generated visual graph derived from the Capability Abstraction Library; layer-band backgrounds, robustness color-coding, evasion annotations, coverage-gap nodes, and bidirectional click-to-highlight sync between the map and the library panel
- **Capability Abstraction Library** - Structured knowledge workspace with a dedicated Capability Library page plus in-Workbench usage, reusing the same baseline/org-custom capability schema to ground AI generation in concrete detection layers (Tool → API → COM/IPC → Registry → Protocol → Process Behavior → Network Behavior)
- **Graph Visualization** - React Flow-based capability abstraction graphs with Auto (library-derived) and Manual modes
- **Detection Strategy** - MITRE ATT&CK technique and strategy selection
- **Deep Dive Sections** - Goal, technical context, blind spots, false positives
- **Testing Guidance** - Test scenarios and expected outputs
- **SOAR Configuration** - Alert triggers, enrichment, containment, notifications
- **Peer Review** - Built-in review request and approval workflow
- **Activity Tracking** - Persistent markdown investigation notes (formatting toolbar included) and activity log per workbench; note clearing is restricted to workbench author/admin
- **Adaptive Workspace Layout** - Right-side metadata/notes panel is collapsible and draggable (up to one-third of the page width), and the Multi-Platform Editor opens fullscreen for maximum editing space
- **Detection Editor Multi-Format Actions** - `GENERATE ALL` supports all registry formats with skip-by-default for non-empty targets, plus an optional **Overwrite all content** toggle; per-format `SAVE {FORMAT}` and `SAVE ALL` are also available in the modal
- **Query Editor Behavior Guide** - Language-specific autocomplete/validation behavior and troubleshooting: `Docs/WORKBENCH_QUERY_EDITOR.md`

### 🤖 AI-Powered Detection Engineering

Multi-provider AI integration for intelligent rule generation:

| Provider | Model selection |
|----------|-----------------|
| **OpenAI** | Enter any valid model identifier (for example `GPT-5.5`) |
| **Google Gemini** | Enter any valid Gemini model identifier (for example `GEMINI-3.5-FLASH`) |
| **Anthropic Claude** | Enter any valid Claude model identifier (for example `CLAUDE-SONNET-4.6`) |
| **Self-hosted/Ollama** | Enter your Ollama model name (for example `llama3.1`, `mistral`) |

Model selection is now **free-text** in user and organization settings, so no frontend redeploy is required when providers publish new model names.

**AI Capabilities:**

- **Logic Deconstruction** - 5-step analysis (capabilities, atomics, evasions)
- **Rule Generation** - Create KQL, Elastic EQL, SPL, Wazuh, or QRadar AQL rules from workbench context
- **RAG Template Grounding** - Language-aware Qdrant retrieval (`KQL`/`EQL`/`SPL`) for grounded syntax/schema/logic generation
- **Improvement Suggestions** - AI-powered rule optimization recommendations
- **ACH Generation** - Generate hypotheses and evidence from scenarios
- **Bias Detection** - Analyze ACH matrices for cognitive biases

📖 RAG details: `Docs/README_RAG_GROUNDING.md`

### 📊 MITRE ATT&CK Integration

Full integration with MITRE ATT&CK framework:

- **Coverage Map** - Interactive ATT&CK Navigator showing detection coverage
- **Technique Mapping** - Link detections to Enterprise, ICS, and Mobile techniques
- **Detection Strategies** - Import MITRE detection strategies and analytics
- **Data Components** - Map required data sources to techniques

### 🔄 Rule Repository Management

Bidirectional synchronization with Git repositories:

**Inbound (Git → HEFAISTOS):**

- Automatic/scheduled repository pulls
- KQL/SPL/WAZUH file parsing with metadata extraction
- KQL file support (`.kql`, `.kusto`, Markdown with code blocks)
- Rule deduplication and updates
- RAG template sync into Qdrant (`JSONL`/`KQL`/`EQL`/`SPL`)

**Outbound (HEFAISTOS → Git):**

- Push workbenches as detection rules (KQL/SPL/WAZUH)
- GitHub Pull Request integration
- Automatic branch creation
- Configurable target paths

### 🕵️ Threat Intelligence Integration

MISP integration for threat-informed detection:

- **IoC Extraction** - IPs, domains, URLs, hashes, emails
- **Event Polling** - Automatic MISP event ingestion
- **Workbench Creation** - Auto-generate workbenches from events
- **ATT&CK Mapping** - Galaxy cluster technique mapping
- **SOAR Pre-population** - Default enrichment/triage steps

### 📋 Analysis of Competing Hypotheses (ACH)

Structured intelligence analysis tool:

- **Evidence Tracking** - Add evidence with credibility ratings
- **Hypothesis Management** - Create and organize competing hypotheses
- **Consistency Matrix** - Score evidence against hypotheses (CC/C/N/I/II)
- **Bias Detection** - AI-powered cognitive bias identification
- **Workbench Linking** - Convert hypotheses to detection workbenches

### 👥 Collaboration & Workflow

Enterprise-grade collaboration features:

**Lifecycle Management:**

```
IDEA → RESEARCH → DEVELOPMENT → REVIEW → APPROVED → TESTING → DEPLOYED → TUNING
```

**Review Workflow:**

- Submit for peer review
- Comment threads
- Approve/reject with feedback
- Activity audit log

**Multi-Tenancy:**

- Organization-based isolation
- Shared templates across entities
- Entity hierarchy (MSSP support)
- Role-based access control

### 📚 Additional Features

| Feature | Description |
|---------|-------------|
| **Knowledge Base** | Wiki-style documentation with categories and Markdown |
| **Data Catalog** | Data source registry with field schemas |
| **News & Announcements** | Platform-wide updates with priorities and auto-expiration |
| **Log Catalog** | Log source management with MITRE mapping |
| **Notification System** | In-app and email notifications |
| **Kanban Board** | Visual workflow management |
| **Tag System** | Flexible tagging across all entities |

---

## 🚀 Quick Start (Manual, Recommended)

```bash
git clone -b main https://github.com/hefaistos-platform/hefaistos.git
cd hefaistos
git pull origin main
cp .env.template .env
cp docker-compose.override.yml.template docker-compose.override.yml
mkdir -p .secrets
openssl rand -base64 32 > .secrets/db_password
openssl rand -base64 32 > .secrets/rabbitmq_pass
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > .secrets/field_key
echo "your-mailgun-key" > .secrets/mailgun_api
make up
make migrate
docker compose exec backend python manage.py createsuperuser
```

For startup profile mapping and service counts, see [Docs/compose-service-matrix.md](Docs/compose-service-matrix.md).

**Estimated Time:** 10-20 minutes | **Estimated Cost:** Free (all open source)

### SHARP Clean Bootstrap (Destructive Reset)

For SHARP fast-track rollout on a clean environment, use:

```bash
./scripts/sharp_bootstrap.sh
```

This executes `docker compose down -v`, rebuilds images, starts core + worker + observability services, runs migrations, rebuilds search indexes, and executes smoke checks.

PostgreSQL 18+ compatibility note: SHARP uses `/var/lib/postgresql` mount layout. If you encounter DB startup errors mentioning `unused mount/volume` and `/var/lib/postgresql/data`, remove old legacy DB volumes and rerun bootstrap.

---

## 📚 Documentation Index

- Full installation guide: [INSTALL_MANUAL.md](Docs/INSTALL_MANUAL.md)
- Authentication setup guide (Entra OIDC + Generic OIDC): [AUTH_SETUP.md](Docs/AUTH_SETUP.md)
- Detection Chokepoints guide: [README_CHOKEPOINTS.md](Docs/README_CHOKEPOINTS.md)
- Maieutic Engine guide: [README_MAIEUTIC.md](Docs/README_MAIEUTIC.md)
- Waiting Room / Workbench intake guide (MISP-only ingestion, import ledger, auto-pull): [WAITING_ROOM_WORKBENCH.md](Docs/WAITING_ROOM_WORKBENCH.md)
- SHARP clean bootstrap operator runbook: [scripts/SHARP_BOOTSTRAP_RUNBOOK.md](scripts/SHARP_BOOTSTRAP_RUNBOOK.md)
- SHARP acceptance checklist template: [scripts/SHARP_ACCEPTANCE_REPORT_TEMPLATE.md](scripts/SHARP_ACCEPTANCE_REPORT_TEMPLATE.md)

---

## 📖 Manual Installation

Use this workflow for all supported installations:

### 1. Clone the repository

```bash
git clone -b main https://github.com/hefaistos-platform/hefaistos.git
cd hefaistos
git pull origin main
```

If you already cloned the repo earlier, switch to `main` before installing:

```bash
git checkout main
git pull origin main
```

### 2. Copy configuration templates

```bash
cp .env.template .env
cp docker-compose.override.yml.template docker-compose.override.yml
```

`docker-compose.yml` now loads `.env` via `env_file` for backend/workers/connectors, so `.env` is the single source of truth for non-secret runtime configuration.

By default, Nginx is published as host `80 -> 8080` and `443 -> 8443`.
If those host ports are occupied, remap only in `docker-compose.override.yml` (keep container ports `8080/8443` unchanged), for example:

```yaml
services:
  nginx:
    ports:
      - "8080:8080"
      - "4443:8443"
```

### 3. Generate secrets

```bash
mkdir -p .secrets
openssl rand -base64 32 > .secrets/db_password
openssl rand -base64 32 > .secrets/rabbitmq_pass
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > .secrets/field_key
# Optional: only needed for the threat_intel_connector (MISP → auto-hunt creation)
# echo "your-misp-api-key" > .secrets/misp_key
echo "your-mailgun-key" > .secrets/mailgun_api
```

If `.secrets/field_key` already exists but is empty, regenerate it before starting Docker:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > .secrets/field_key
# Fallback if Python cryptography is unavailable:
# openssl rand 32 | openssl enc -base64 -A | tr '+/' '-_' > .secrets/field_key
```

### 4. Configure environment

- **Recommended:** Edit [.env](.env) from [.env.template](.env.template)
- Optional: export environment variables in your shell to override `.env` values for a single run
- Keep secrets in Docker secrets under `/run/secrets/*` (do not put secrets in `.env`)

Key variables:

```bash
PUBLIC_BASE_URL=https://your.domain.com
FRONTEND_URL=https://your.domain.com
CORS_ALLOWED_ORIGINS=https://your.domain.com
CSRF_TRUSTED_ORIGINS=https://your.domain.com
SERVER_DOMAIN=your.domain.com
ADMIN_ALLOWED_IP_RANGES=192.168.1.0/24
```

### 5. Start the platform

```bash
make up
```

Optional profile layers:

```bash
make up-workers    # scheduler + async workers
make up-obs        # elasticsearch + qdrant
make up-devtools   # connector services
make up-full       # core + workers + obs + devtools
```

Rollback path (legacy always-on behavior): `make up-full`.

### 6. Run migrations and create superuser

```bash
make migrate
docker compose exec backend python manage.py createsuperuser
```

### 7. Import MITRE ATT&CK data

```bash
docker compose exec backend python manage.py import_mitre_universal --mitre-version 19.0 --mode remote
```

### 8. Access the platform

- Web UI: `https://your.domain.com`
- GraphQL API: `https://your.domain.com/graphql`
- Admin Panel: `https://your.domain.com/admin`

---

## 🔧 Configuration

### Environment Variables

For the complete, up-to-date variable catalog (including advanced/optional keys), see [Docs/ENVIRONMENT_VARIABLES.md](Docs/ENVIRONMENT_VARIABLES.md).

| Variable | Description | Required |
|----------|-------------|----------|
| `DEBUG` | Enable debug mode | No (default: False) |
| `SECRET_KEY` | Django secret key | Yes (auto-generated if empty) |
| `SERVER_DOMAIN` | Your domain or IP | Yes |
| `FRONTEND_URL` | Frontend base URL for emails | No (default: https://localhost) |
| `PUBLIC_BASE_URL` | Canonical external base URL for shareable links (for multi-proxy deployments) | No (default: unset; backend tries external FRONTEND_URL, then request host) |
| `WEBAUTHN_RP_ID` | WebAuthn relying party ID (public host) | Yes for security-key MFA/passwordless |
| `WEBAUTHN_ORIGIN` | WebAuthn origin (must be HTTPS in production) | Yes for security-key MFA/passwordless |
| `CORS_ALLOWED_ORIGINS` | Additional allowed CORS origins (comma-separated). `mitre-attack.github.io` is always included automatically. | No |
| `CSRF_TRUSTED_ORIGINS` | Trusted CSRF origins (comma-separated, must include your public URL) | No (default: https://localhost,http://localhost) |
| `ADMIN_ALLOWED_IP_RANGES` | IP ranges allowed to access /admin/ (comma-separated CIDR) | No (default: localhost + Docker networks) |
| `DB_HOST` | PostgreSQL host | No (default: db) |
| `DB_PORT` | PostgreSQL port | No (default: 5432) |
| `DB_NAME` | Database name | No (default: hefaistos_db) |
| `DB_USER` | Database user | No (default: hefaistos_user) |
| `DB_PASSWORD_FILE` | Docker secret file path for DB password | No (default: /run/secrets/db_password) |
| `RABBITMQ_HOST` | RabbitMQ host | No (default: rabbitmq) |
| `RABBITMQ_PORT` | RabbitMQ port | No (default: 5672) |
| `RABBITMQ_USER` | RabbitMQ username | No (default: hefaistos_mq) |
| `RABBITMQ_PASS_FILE` | Docker secret file path for RabbitMQ password | No (default: /run/secrets/rabbitmq_pass) |
| `ELASTICSEARCH_HOST` | Elasticsearch host | No (default: elasticsearch) |
| `ELASTICSEARCH_PORT` | Elasticsearch port | No (default: 9200) |
| `FIELD_ENCRYPTION_KEY_PATH` | Path to Fernet key | No (default: /run/secrets/field_key) |
| `FIELD_ENCRYPTION_KEY_FILE` | Docker secret file path for Fernet key | No (default: /run/secrets/field_key) |
| `MISP_URL` | MISP URL for **threat_intel_connector** only (ADVOPS push uses per-org instances configured via UI) | No |
| `HEFAISTOS_API_URL` | API base URL used by connector containers | No (default: http://backend:8000/graphql) |
| `HEFAISTOS_API_TOKEN_FILE` | Connector service token file path | No (default: /run/connector/token.jwt) |
| `EMAIL_ENABLED` | Enable email notifications | No (default: False) |
| `EMAIL_HOST` | SMTP host | No |
| `EMAIL_PORT` | SMTP port | No |
| `EMAIL_HOST_USER` | SMTP username | No |
| `MAILGUN_API_KEY_PATH` | Path to Mailgun API key | No |

### Docker Secrets

Production deployments should use Docker secrets:

```yaml
secrets:
  db_password:
    file: ./.secrets/db_password
  rabbitmq_pass:
    file: ./.secrets/rabbitmq_pass
  field_key:
    file: ./.secrets/field_key
  # misp_key is only required if using the threat_intel_connector
  misp_key:
    file: ./.secrets/misp_key
  mailgun_api:
    file: ./.secrets/mailgun_api
```

### CORS & Security Key (YubiKey/WebAuthn) Setup

CORS/CSRF and WebAuthn are configured through `.env` values (loaded by Compose via `env_file`). `.env.template` is the starter template.

#### For users

To enroll a YubiKey/security key, users only need the UI:

1. Log in to HEFAISTOS.
2. Open **User Profile**.
3. Find **Security Keys (YubiKey/WebAuthn)**.
4. Optionally enter a key name.
5. Click **Add Security Key**.
6. Touch/confirm the YubiKey when the browser prompts.
7. Enrollment is complete.

Users do **not** need to edit `.env`, Docker Compose, or any server-side settings.

#### For administrators/operators (one-time platform setup)

Configure these values in `.env`:

```bash
FRONTEND_URL=https://detect.hefaistos.org
PUBLIC_BASE_URL=https://detect.hefaistos.org
WEBAUTHN_RP_ID=detect.hefaistos.org
WEBAUTHN_ORIGIN=https://detect.hefaistos.org
```

`PUBLIC_BASE_URL` is recommended when your deployment has multiple proxy layers (for example: External LB/Proxy -> Nginx -> frontend/backend containers). It ensures generated share URLs use the real externally reachable origin.

Also set CORS/CSRF values in `.env` (`CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`).

After updating `.env`, restart the services that consume these values:
```bash
docker compose --profile workers up -d --force-recreate backend scheduler opentide-hef-publish-worker opentide-hef-import-worker listener ai_generation_worker opentide_enrichment_worker
```

> **Note:** Since the frontend and backend are both served by the same Nginx proxy on the same origin, CORS between them is not required. `CORS_ALLOWED_ORIGINS` is only needed for external tools (such as the ATT&CK Navigator at `mitre-attack.github.io`) that need to fetch data from the API.

**Media CORS**: Media files (avatars, snapshots) are served directly by Nginx with open CORS headers by default (`Access-Control-Allow-Origin: *`), so avatars load from any origin without configuration. If you need to restrict this, modify the `/media/` location block in `nginx/conf.d/hefaistos.conf`.

---

### SSL/TLS Configuration

Place certificates in `nginx/certs/`:

- `nginx/certs/hefaistos.crt` - SSL certificate
- `nginx/certs/hefaistos.key` - SSL private key

Self-signed certificates can be generated:

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/hefaistos.key \
  -out nginx/certs/hefaistos.crt \
  -subj "/CN=localhost"
```

---

## 👤 User Roles

| Role | Permissions |
|------|-------------|
| **ADMIN** | Full access: user management, organization settings, Git operations, all CRUD |
| **REVIEWER** | Review and approve playbooks, push to Git, manage rules |
| **ANALYST** | Create/edit playbooks and rules, submit for review |
| **VIEWER** | Read-only access to playbooks, rules, and dashboards |
| **ELONE** | Read-only access to L1 Portal (L1 Analysts) |
| **BOT_AUDITOR_ORG** | Organization-scoped bot auditor role for automated auditing workflows |
| **BOT_AUDITOR_GLOBAL** | Global bot auditor role for cross-organization automated auditing workflows |

### Setting User Roles

Via Django Admin:

```bash
docker compose exec backend python manage.py shell
>>> from identity.models import CustomUser
>>> user = CustomUser.objects.get(username='analyst1')
>>> user.role = 'ADMIN'  # or 'ANALYST', 'REVIEWER', 'VIEWER', 'ELONE', 'BOT_AUDITOR_ORG', 'BOT_AUDITOR_GLOBAL'
>>> user.save()
```

---

## 🔌 Event-Driven Connectors

HEFAISTOS uses RabbitMQ for event-driven integrations:

### Rule Connector

Synchronizes detection rules from Git repositories.

- **Trigger:** `rule.repo.pull.requested`
- **Function:** Clone repo, parse KQL/SPL/WAZUH files, upsert rules
- **RAG Trigger:** `rule.repo.rag.sync.requested`
- **RAG Function:** Clone repo, ingest `JSONL`/`KQL`/`EQL`/`SPL` templates, sync to Qdrant

### Notification Connector

Creates in-app notifications from domain events.

- **Events:** Review requests, approvals, rule creation, status changes
- **Channels:** In-app, email (configurable per user)

### Threat Intel Connector

Integrates with MISP threat intelligence platform.

- **Trigger:** Polling interval (configurable)
- **Function:** Import events, extract IoCs, create workbenches

### Git Push Connector

Exports playbooks to Git repositories as detection rules.

- **Trigger:** `playbook.git.push.requested`
- **Function:** Format rule (KQL/SPL/WAZUH), create branch, push, optionally open PR

### Deploy Connector

Handles deployment workflow transitions.

- **Trigger:** `playbook.deploy.requested`
- **Function:** Update playbook status to DEPLOYED

### Threat Intelligence Intake (MISP-Only, No Direct API Push)

HEFAISTOS never accepts a direct API push of a Waiting Room case from another
tool. The only intake path is `importWaitingCasesFromMisp`, which pulls from a
configured MISP instance (manually, or on a per-instance auto-pull schedule).
Third-party tools (KQL Striker, DragonNews, or anything else) that want to land
findings in the Waiting Room build a MISP event carrying a structured MISP
Object — see the `capability-abstraction` object template and exporter at
`/Volumes/Data/Scripts/dragonnews-misp/misp-objects/capability-abstraction/` for
a worked example — tag it `HEFAISTOS`, and push it to MISP (directly, or via a
Git repo consumed by MISP). HEFAISTOS then pulls it in on the next import.

See `Docs/WAITING_ROOM_WORKBENCH.md` for the full ingestion model, the
import ledger's permanence semantics, and auto-pull configuration.

---

## ⚠️ Breaking Changes

### SIGMA format removed (2026)

SIGMA/Sigma YAML is no longer supported as a detection rule format in HEFAISTOS.

**What changed:**
- `SIGMA` removed from all rule format choices, selectors, and API fields
- `sigconverter` service removed from `docker-compose.yml` (port 7002)
- pySigma Python packages removed from backend dependencies
- `StartGenerateSigmaTask` GraphQL mutation renamed to `StartGenerateRuleTask`
- `GenerateSigmaAI` GraphQL mutation removed
- Rule conversion UI (pySigma backend conversion) removed
- `rules/sigma` Git push folder option removed

**Migration steps after `git pull origin main`:**

1. Rebuild and restart all containers:
   ```bash
   docker compose down
   docker compose pull
   docker compose up -d --build
   ```

2. Apply database migrations (remaps existing SIGMA rules → OTHER format):
   ```bash
   docker compose exec backend python manage.py migrate
   ```

3. Clean up your environment:
   - Remove `LSP_SIGMA_*`, `SIGCONVERTER_*` variables from `.env` / deployment configs
   - Remove any SIGMA-specific automation from your deployment pipeline

4. Verify service health — backend, worker, frontend, and remaining LSP services (KQL/SPL/WAZUH/AQL) should all start cleanly.

5. Review legacy SIGMA rules:
   - Existing rules with `format=SIGMA` have been automatically remapped to `format=OTHER` by the migration
   - Recreate affected rules in a supported format (KQL, SPL, WAZUH) if needed

**Supported formats going forward:** KQL, SPL, WAZUH, EQL, ELASTIC, OTHER

---

## 📖 API Reference

### GraphQL Endpoint

`POST /graphql`

**Authentication:** Bearer token (JWT)

```bash
curl -X POST https://localhost/graphql \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ me { id username role } }"}'
```

### Key Queries

```graphql
# Get current user
query { 
  me { 
    id 
    username 
    email 
    role 
    organization { name } 
  } 
}

# List playbook graphs
query { 
  allPlaybookGraphs { 
    id 
    title 
    status 
    author { username } 
  } 
}

# Search rules
query { 
  rulesConnection(search: "mimikatz", first: 10) { 
    edges { 
      node { 
        id 
        title 
        format 
        rawContent 
      } 
    } 
    totalCount 
  }
}

# Get MITRE technique suggestions
query { 
  detectionSuggestions(techniqueId: "T1003") { 
    technique { 
      id 
      name 
    }
    strategies { 
      id 
      name 
      analytics { 
        name 
        description 
      } 
    }
  }
}
```

### Key Mutations

```graphql
# Create playbook graph
mutation { 
  createPlaybookGraph(title: "New Detection") { 
    graph { id } 
  } 
}

# Generate AI rule
mutation { 
  startGenerateRuleTask(outputFormat: "KQL") { 
    taskId 
  } 
}

# Submit for review
mutation { 
  requestReview(graphId: "uuid") { 
    success 
    message 
  } 
}

# Approve review
mutation { 
  approveReview(reviewId: "uuid") { 
    success 
  } 
}
```

---

## 🧪 Development

### Local Development Setup

1. **Backend:**

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

2. **Frontend:**

```bash
cd frontend
npm install
npm start
```

3. **Services (Docker):**

```bash
docker compose up -d db rabbitmq elasticsearch
```

### Running Tests

```bash
# Backend tests
docker compose exec backend python manage.py test

# Frontend tests
docker compose exec frontend npm test

# Coverage report
cd backend && coverage run --source='.' manage.py test && coverage report
```

### Database Migrations

```bash
# Create new migration
cd backend && python manage.py makemigrations app_name

# Apply migrations
python manage.py migrate

# Check migration status
python manage.py showmigrations
```

### GraphQL Debugging

Interactive GraphQL playground:

- Via NGINX proxy (Compose): `http://localhost/graphql` or `https://localhost/graphql`
- Direct backend (when running `manage.py runserver`): `http://localhost:8000/graphql`

See [DEBUG_GRAPHQL.md](Docs/DEBUG_GRAPHQL.md) for detailed query examples.

### Code Style

- **Backend:** Black, isort, flake8
- **Frontend:** ESLint, Prettier

---

## 📁 Project Structure

```
hefaistos/
├── backend/                    # Django backend
│   ├── core/                   # Core settings, schema, middleware
│   ├── identity/               # User auth, profiles, RBAC
│   ├── organizations/          # Multi-tenant organization management
│   ├── playbooks/              # Detection playbooks and graphs
│   ├── rules/                  # Detection rule management
│   ├── ach/                    # Analysis of Competing Hypotheses
│   ├── ai_assistant/           # AI integration engine
│   ├── platform_data/          # MITRE ATT&CK data
│   ├── knowledge/              # Knowledge base
│   ├── data_catalog/           # Data source catalog
│   ├── log_catalog/            # Log source management
│   ├── review/                 # Peer review workflow
│   ├── notifications/          # Notification system
│   ├── news/                   # Announcements
│   ├── tags/                   # Tagging system
│   └── services/               # Event listener service
├── frontend/                   # React frontend
│   ├── src/
│   │   ├── components/         # Reusable UI components (incl. CapabilityAbstractionMapNode, TechniqueRootNode, CoverageGapNode, CapabilityAbstractionLayerBands)
│   │   ├── pages/              # Page components
│   │   ├── context/            # React context providers
│   │   └── utils/              # Utility functions (incl. capabilityAbstractionUtils)
│   └── public/                 # Static assets
├── hefaistos-sdk/              # Python SDK for connectors
├── rule_connector/             # Git rule sync connector
├── notification_connector/     # Notification connector
├── threat_intel_connector/     # MISP integration connector
├── git_push_connector/         # Git export connector
├── deploy_connector/           # Deployment connector
├── nginx/                      # Nginx configuration
├── scripts/                    # Utility scripts
├── attack-navigator/           # MITRE Navigator static build
├── Docs/                       # Additional documentation
├── docker-compose.yml          # Docker orchestration
└── README.md                   # This file
```

---

## ⚙️ Maintenance & Operations

### Backup & Restore

Backups can be run manually and optionally scheduled via cron:

```bash
# Manual backup to default ./backups
./scripts/backup-hefaistos.sh

# Backup to external mounted media (admin-managed)
./scripts/backup-hefaistos.sh --backup-dir /mnt/backup-drive/hefaistos --retention-days 30

# Restore from a backup archive
./scripts/backup-hefaistos.sh --restore /path/to/hefaistos-backup-YYYYmmdd_HHMMSS.tar.gz
```

Backups include:

- PostgreSQL database dump (gzip compressed)
- Runtime media and navigator data volumes
- Configuration files and secrets
- Integrity verification checksums
- Automatic rotation with 30-day retention (configurable)

Elasticsearch snapshots are intentionally not part of this backup script. If needed after restore:

```bash
docker compose exec backend python manage.py search_index --rebuild -f
```

**See:** [scripts/backup-hefaistos.sh](scripts/backup-hefaistos.sh)

### Uninstall & Rollback

To safely remove HEFAISTOS:

```bash
# Interactive uninstall with options
./scripts/uninstall-hefaistos.sh

# Keep data and backups (rollback-friendly)
./scripts/uninstall-hefaistos.sh --keep-data --keep-backups

# Full cleanup (use with caution)
./scripts/uninstall-hefaistos.sh --full-cleanup
```

**See:** [scripts/uninstall-hefaistos.sh](scripts/uninstall-hefaistos.sh)

### Firewall Configuration

Configure UFW firewall:

```bash
# Interactive firewall setup
./scripts/setup-firewall.sh

# View firewall rules
sudo ufw status verbose

# Manual rule examples (NGINX public ports)
sudo ufw allow from 192.168.0.0/16 to any port 443
sudo ufw allow from 192.168.0.0/16 to any port 80
```

**See:** [scripts/setup-firewall.sh](scripts/setup-firewall.sh)

### Service Management

```bash
# Start core services only (default)
make up

# Start full runtime (core + workers + obs + devtools)
make up-full

# Start workers only (on top of core)
make up-workers

# Run one-shot migration
make migrate

# Run one-shot seed tasks
make seed

# Stop and remove stack
make down

# View status
make ps

# Follow logs
make logs
```

---

## 🔒 Security Considerations

- **Authentication:** JWT tokens with configurable expiration
- **Authorization:** Role-based access control (RBAC)
- **Encryption:** Fernet encryption for sensitive fields (API keys, tokens)
- **Secrets:** Docker secrets for production credentials
- **Network:** Internal Docker network isolation
- **HTTPS:** TLS termination at Nginx reverse proxy
- **CORS:** Configurable allowed origins

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Dependency License Compliance (PR Gate)

To reduce legal risk for SaaS/commercial deployment, this repository enforces
dependency license checks on pull requests using GitHub's Dependency Review Action.

- Workflow: `.github/workflows/dependency-review.yml`
- Policy config: `.github/dependency-review-config.yml`
- Status check name: `dependency-review`

The check fails when a PR introduces dependencies (runtime or development scope)
with denied licenses, currently including:

- `AGPL-1.0-only`
- `AGPL-1.0-or-later`
- `AGPL-3.0-only`
- `AGPL-3.0-or-later`
- `SSPL-1.0`
- `OSL-3.0`
- `CC-BY-NC-4.0`

#### If your PR fails on license policy

1. Identify the package flagged by the `dependency-review` check.
2. Replace it with an alternative package under a permitted license.
3. If replacement is not feasible, open an issue describing:
   - package name and version
   - where it is used
   - why no suitable alternative exists
   - legal/compliance impact
4. Wait for maintainer approval before requesting any policy exception.

No direct bypass is allowed on protected branches when `dependency-review` is
configured as a required status check.

---

## 📄 License

This project is licensed under the **GNU Affero General Public License v3.0** (`AGPL-3.0-only`).

See [LICENSE](./LICENSE) for the full text.

### Commercial Use & SaaS

- Commercial use is permitted.
- Third parties may fork and run/sell it as a service.
- If they modify the software and provide it over a network, AGPL requires them to provide the corresponding source code of those modifications to users of that service.

If someone needs a proprietary exception, separate commercial terms can be offered by the maintainer.

---

## 📞 Support

For support and inquiries:

- Open an issue in the GitHub repository
- Contact the HEFAISTOS team

---

<div align="center">

**Built with ❤️ for Detection Engineers**

</div>

**(c) 2026 th3r3d - dev + th30ne -managing croak (Both DCG420) & A Collective Hallucination of AI Bots**

Provided "as is", without warranty of any kind. See `LICENSE` for details.
