# Node 24 runtime upgrade assessment

Checked on **26 October 2026**. This change prepares the upgrade; production
deployment and service integration checks have not been performed.

## Prepared changes

| Component | Previous configuration | Prepared version |
| --- | --- | --- |
| Frontend Node | Floating `24-bookworm-slim` | `24.22.1-bookworm-slim` |
| Backend Node (SyntaxTide) | NodeSource Node 20 | `24.22.1`, copied from the official Bookworm image |
| npm, both images | `11.17.0` | `11.19.1` |
| Node TypeScript definitions | `26.0.1` | `24.19.2` (Node 24 definitions) |
| React / React DOM | `19.2.0` | `19.2.9` |
| Apollo Client | `3.11.0` | `3.14.1` |
| GraphQL JS | `16.11.0` | `16.14.2` |
| React Router DOM | `7.9.5` | `7.18.4` |
| Drag and drop | `@hello-pangea/dnd` `16.6.0` | `18.0.1` |
| Tailwind / Tailwind PostCSS | `4.3.1` | `4.3.3` |
| shell-quote override | `1.9.0` | `1.12.0` |

Node **24.22.1** is the latest Node 24 LTS release, published on 20 October
2026 as a security release. It bundles npm **11.19.1**. These are the requested
versions; newer releases exist on the Node 26 and npm 12 lines. npm 11.19.1
requires Node `^20.17.0 || >=22.9.0`; Node 24.22.1 satisfies it. Vite 8.3.5
requires Node `^20.19.0 || >=22.12.0`, which is also satisfied.

Both Docker builds assert the exact Node/npm versions. The backend keeps Python
3.12 and Debian Bookworm, installs Node's system library dependencies, and
provides `node`, `nodejs`, `npm`, and `npx`. This removes the NodeSource installer
and the older backend runtime. The verified official Node image tag has amd64,
arm64 and ppc64le variants; local execution checks used macOS arm64.

Root and frontend `.nvmrc` files select Node 24.22.1. Both manifests record the
supported Node/npm ranges and exact package manager. The frontend `.npmrc`
preserves the existing legacy peer resolution for local installs, Docker and CI.
The retained `react-scripts` test runner declares older React/TypeScript peers;
it still needs this policy. The frontend `.dockerignore` prevents host
`node_modules` from overwriting dependencies installed for Linux during a build.

## Compatibility findings

- Drag-and-drop 16.6.0 declares support through React 18. Version 18.0.1 supports
  React 19. Its real keyboard lift, move and drop behavior passes a new StrictMode
  regression test; the existing Kanban suite mocks this library.
- Apollo 3.14.1 accepts React 19 and preserves the app's existing Apollo 3 API.
  `apollo-upload-client` 19 requires Apollo 4. It was unused and has been removed:
  `src/apollo-client.ts` implements multipart uploads with its own Apollo link.
  Real backend file upload remains a staging check.
- React Router 7.18.4 addresses the advisories reported against 7.9.5. Login,
  Kanban, rule detail and other previously passing routing tests still pass.
- Tailwind/PostCSS and shell-quote updates address audit findings while keeping
  the established build configuration.
- The SyntaxTide bridge omitted the language server's required `--stdio` flag.
  A real server handshake reproduced the startup failure. The bridge now passes
  the flag and spawns `process.execPath`, so its child uses the same Node binary.
  A regression test verifies split LSP frame forwarding with no Node on `PATH`.
- Node definitions now match the runtime. Adding `node` to TypeScript's explicit
  type list fixes missing `process`, `global`, and `NodeJS` definitions. Two fetch
  mocks now use the typed Jest overload.

## Validation results

Tests used an isolated Node 24.22.1 distribution verified against the official
SHA256 list, with npm 11.19.1. Python checks used an isolated Python 3.12 environment
installed from the unchanged backend requirements; `pip check` passed.

| Check | Result |
| --- | --- |
| Clean frontend `npm ci` | Pass |
| Production Vite build before and after dependency changes | Pass |
| Full baseline frontend suite on Node 24.22.1 | 28 suites passed, 6 failed; 150 tests passed, 7 failed |
| Full upgraded frontend suite | 29 suites passed, 6 failed; 151 tests passed, 7 failed |
| Added real React 19 keyboard drag-and-drop test | Pass |
| Focused compatibility test set used by the new CI workflow | All 9 suites / 52 tests passed locally |
| Added Node bridge transport regression test | Pass |
| Existing Python LSP manager, routing and status tests | All 18 passed via unittest after Django setup |
| Upstream SyntaxTide clean install and TypeScript compilation | Pass |
| Real SyntaxTide through the TCP bridge | Initialization, 131 SPL completion items and shutdown passed |
| TypeScript comparison | 31 baseline errors reduced to 18; no new error locations/messages |
| Frontend lockfile audit | 70 findings reduced to 65; critical findings reduced from 1 to 0 |
| Manifest/lockfile consistency and workflow YAML | Pass |
| Linux Docker image builds and running platform services | Pending; Docker is unavailable in this workspace |

The live SyntaxTide check used upstream commit
`051e6d0c109194a46e4dc3db06c0389330c50bbc`. The manager still follows upstream
updates at startup, so future upstream changes are outside these results.

The same six frontend suites fail before and after the upgrade:
`App`, `MaieuticEngineModal`, `ConfigurationPage.repos`,
`ConfigurationPage.systemUpdate`, `WorkbenchSectionControls`, and
`RegistrationPage`. Failures include existing Jest ESM/module resolution,
outdated UI assertions and incomplete workbench fixtures. The type check also
retains existing application/test errors. These results do not establish that
every platform feature works. Remaining audit findings include the legacy
`react-scripts` toolchain; do not use `npm audit fix --force` as a substitute for
a test-runner migration.

The normal Django test command attempts PostgreSQL-specific migrations against
the SQLite fallback and fails with `near "AS": syntax error`. The 18 database-free
LSP tests were therefore run directly after Django setup. Full backend tests need
the platform's PostgreSQL configuration.

The new `Runtime compatibility` workflow verifies the requested runtime, builds
the frontend, runs focused auth/routing/rule/reporting/drag-and-drop tests, and
builds both production images. It also checks the backend image's actual Node/npm
binaries. It supplements the existing backend CI; the full frontend suite's
known failures are not treated as passing.

## Other core upgrade candidates

Versions below were checked against upstream registries/releases on the date
above. They are recommendations; service image pins and Python requirements
have not been changed in this runtime upgrade.

| Component | Current | Candidate | Compatibility and rollout requirement |
| --- | --- | --- | --- |
| Nginx, proxy and frontend | `1.28.0-alpine` | `1.28.3-alpine` maintenance patch; stable line is `1.30.6` | Update both pins together; check `nginx -t`, TLS, SPA fallback, GraphQL uploads, WebSockets and static/media/Navigator paths. |
| PostgreSQL | `18.4` | `18.6` | Stay on major 18 and preserve `postgres_data_v18:/var/lib/postgresql`; verify backup/restore, migrations and GraphQL queries. PostgreSQL 19 is a release candidate and should not be adopted here. |
| RabbitMQ | `4.3.2-management` | `4.3.7-management` | Maintenance release on the same series; official image supplies compatible Erlang. Verify publisher/consumer acknowledgements, retry/cancel handling, persistence and all worker queues. Latest 4.4.0 needs a separate review. |
| Elasticsearch | Server `9.3.6`, client `9.3.0`, Django DSL `9.0` | Server `9.3.8` maintenance patch; latest server `9.5.5`, client `9.5.1` | Prefer the same server minor initially; snapshot and verify indexing, searches and `search_index --rebuild`. Review the server/client pair before moving to 9.5. |
| Qdrant | `v1.13.4` | `v1.13.6` maintenance patch; latest `v1.20.0` | Snapshot collections and verify RAG ingestion, filters and retrieval. Review intervening release notes and storage migration requirements before jumping to 1.20. |
| Python | Floating `3.12-slim-bookworm` | Current 3.12 image resolves to `3.12.15` | Rebuild with `--pull` for patch refreshes; consider an explicit patch or digest for reproducibility across all six Python images. Review native dependencies before a Python minor upgrade. |
| Django | `6.0.8` | `6.0.9` maintenance patch; latest `6.1.2` | Validate Graphene/JWT/auth, middleware, migrations and backend tests against PostgreSQL before changing the pin. |
| Channels / Daphne | `4.3.2` / `4.2.2` | Channels already latest; Daphne `4.2.3` | Verify ASGI/LSP WebSockets and process startup. |
| PostgreSQL / AMQP clients | psycopg2 `2.9.11`, pika `1.3.2` | `2.9.13` / `1.4.4` | Verify DB transactions and worker publish/consume/reconnect behavior with the running services. |
| Other frontend foundations | Ant Design `6.4.5`, TypeScript `6.0.3`, Recharts `2.10.3`, Monaco `0.50.0` | `6.6.8`, `7.0.2`, `3.10.1`, `0.57.0` respectively | Separate changes: existing Ant Design type errors and major compiler/chart changes need targeted UI verification. Vite `8.3.5` is already latest. |
| Existing backend GitHub actions | checkout/setup-python v3 | v7 | Review runner requirements and migrate separately. New runtime CI uses checkout/setup-node v7 on hosted `ubuntu-latest`. |

The root JavaScript package has a separate dependency tree, including Ant Design
5 and TypeScript 5. The application is installed and built from `frontend`; use
that directory for application dependency upgrades and validation.

## Staging deployment and rollback

On a Docker-capable staging host with its normal `.env` and secrets:

```sh
docker compose config --quiet
docker compose build --pull backend frontend
docker compose run --rm --no-deps backend node --version
docker compose run --rm --no-deps backend npm --version
docker compose --profile workers up -d --wait
docker compose exec backend python manage.py lsp_status
```

Include any connector/observability profiles used by that installation. The
shared backend build is used by workers as well as the web service, so recreate
all enabled services that use it. Check login/logout and token refresh, protected
routes, GraphQL queries/mutations and file uploads, Kanban drag/drop, rule editing
and autocomplete, workbench import/export, AI tasks, reports, Navigator coverage,
and queued connector jobs. Run the full backend suite against an isolated
PostgreSQL test database, and retain the frontend baseline failure comparison.

Save the previous backend/frontend image IDs before deployment. This change adds
no database migrations or service-data upgrades. Roll back by restoring those
image references and recreating the affected backend/frontend/worker services;
keep the existing persistent volumes. State-service candidates above require
their own backups and rollback plans before deployment.

## Sources

- [Official Node release index](https://nodejs.org/dist/index.json)
- [Node 24.22.1 checksums](https://nodejs.org/dist/v24.22.1/SHASUMS256.txt)
- [Official Node Bookworm build](https://github.com/nodejs/docker-node/blob/main/24/bookworm-slim/Dockerfile)
- [npm 11.19.1 registry metadata](https://registry.npmjs.org/npm/11.19.1)
- [Nginx releases](https://nginx.org/en/download.html)
- [PostgreSQL image tags](https://hub.docker.com/_/postgres/tags)
- [RabbitMQ 4.3.7 release notes](https://github.com/rabbitmq/rabbitmq-server/releases/tag/v4.3.7)
- [Elasticsearch releases](https://github.com/elastic/elasticsearch/releases)
- [Qdrant releases](https://github.com/qdrant/qdrant/releases)
- [Django package metadata](https://pypi.org/pypi/Django/json)
- npm package metadata and `npm audit --package-lock-only --json` for frontend findings.
