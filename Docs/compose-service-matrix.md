# Compose Service Matrix

## Startup Mode Counts

| Mode | Before (no profiles) | After (profile-based) |
|---|---:|---:|
| Default `docker compose up -d` | 19 running services | 5 running services |
| Full runtime (`workers` + `obs` + `devtools`) | 19 running services | 19 running services |
| One-shot operational tasks (`batch`) | N/A | 2 task services (`migrate`, `seed`) |

## Current → Target Service Mapping

| Service | Role | Target profile | Default start |
|---|---|---|---|
| nginx | edge | core (no profile) | Yes |
| frontend | core app | core (no profile) | Yes |
| backend | core app | core (no profile) | Yes |
| db | stateful | core (no profile) | Yes |
| rabbitmq | stateful | core (no profile) | Yes |
| elasticsearch | stateful/observability | `obs` | No |
| qdrant | stateful/observability | `obs` | No |
| listener | worker | `workers` | No |
| ai_generation_worker | worker | `workers` | No |
| opentide_enrichment_worker | worker | `workers` | No |
| mve_validation_worker | worker | `workers` | No |
| scheduler | worker | `workers` | No |
| opentide-hef-publish-worker | worker | `workers` | No |
| opentide-hef-import-worker | worker | `workers` | No |
| deploy_connector | devtool connector | `devtools` | No |
| notification_connector | devtool connector | `devtools` | No |
| threat_intel_connector | devtool connector | `devtools` | No |
| rule_connector | devtool connector | `devtools` | No |
| git_push_connector | devtool connector | `devtools` | No |
| migrate | one-shot task | `batch` | No |
| seed | one-shot task | `batch` | No |

## Profile Activation Commands

- Core only: `docker compose up -d`
- Add workers: `docker compose --profile workers up -d`
- Add observability/stateful extras: `docker compose --profile obs up -d`
- Add connectors/devtools: `docker compose --profile devtools up -d`
- Full runtime: `docker compose --profile workers --profile obs --profile devtools up -d`
- One-shot migrate: `docker compose --profile batch run --rm migrate`
- One-shot seed: `docker compose --profile batch run --rm seed`
