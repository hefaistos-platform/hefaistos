# Installation

## Purpose
Document the full operator installation workflow for `main` deployments.

## Audience
Administrators responsible for production-style installation and baseline configuration.

## Prerequisites
- Runtime prerequisites from [Prerequisites](prerequisites.md)
- Access to deployment domain and TLS materials

## Steps / Workflow
1. Clone and prepare repository from `main`.
2. Create Docker secret files.
3. Configure `.env` (URLs, CORS/CSRF, domain, auth settings).
4. Run SHARP clean bootstrap or equivalent compose workflow.
5. Run post-install initialization tasks (migrations, superuser, ATT&CK import).

## Validation / Expected result
All required services start and essential post-install tasks complete without errors.

## Troubleshooting
Use `Docs/INSTALL_MANUAL.md` troubleshooting sections for DB volume compatibility and runtime startup errors.

## Related pages
- [Quick Start](quick-start.md)
- [Environment Variables](../configuration/environment-variables.md)
- [System Update](../operations/system-update.md)
