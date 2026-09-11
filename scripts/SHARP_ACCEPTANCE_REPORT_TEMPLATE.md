# SHARP Acceptance Report Template

Date:
Operator:
Branch/Commit:

## Version Pin Matrix

| Component | Target | Observed | Status |
| --- | --- | --- | --- |
| Django | 6.0.5 |  |  |
| Python runtime | 3.12 |  |  |
| Node runtime | 24 LTS + npm 11.17.0 |  |  |
| React | 19.2.0 |  |  |
| TypeScript | 6.0.3 |  |  |
| TailwindCSS | 4.3.1 |  |  |
| Ant Design | 6.4.5 |  |  |
| React Flow (`@xyflow/react`) | 12.11.1 |  |  |
| PostgreSQL image | 18.4 |  |  |
| RabbitMQ image | 4.3.2-management |  |  |
| Elasticsearch image | 9.3.6 |  |  |
| NGINX image | 1.28.0-alpine |  |  |

## Functional Smoke Matrix

| Test | Result | Notes |
| --- | --- | --- |
| GraphQL query works (`{__typename}`) |  |  |
| GraphQL mutation works |  |  |
| JWT login (`/api/token`) works |  |  |
| JWT refresh (`/api/token/refresh`) works |  |  |
| GraphQL file upload works |  |  |
| LSP WebSocket `/ws/lsp/` handshake works |  |  |
| LSP message exchange works |  |  |
| Elasticsearch indexing works |  |  |
| Elasticsearch retrieval works |  |  |
| RabbitMQ listener consumes messages |  |  |
| Async workers process tasks |  |  |

## Theme Validation Matrix

| Route | Light | Dark | System | Notes |
| --- | --- | --- | --- | --- |
| Lifecycle Hub (Kanban) |  |  |  |  |
| Coverage Map |  |  |  |  |
| Rule Detail |  |  |  |  |
| Detection Editor Modal |  |  |  |  |
| Login/Auth pages |  |  |  |  |

## Decision Log

- Destructive reset used (`docker compose down -v`): Yes / No
- Data migration performed: No
- Known blockers/deviations:

## Final Sign-Off

- SHARP accepted: Yes / No
- Follow-up actions:
