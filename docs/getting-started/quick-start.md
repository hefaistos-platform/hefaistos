# Quick Start

## Purpose
Provide the fastest recommended manual path to bring up HEFAISTOS.

## Audience
Operators performing a first-time or clean deployment.

## Prerequisites
See [Prerequisites](prerequisites.md).

## Steps / Workflow
1. Clone repository and copy `.env` and compose override templates.
2. Create required secrets in `.secrets`.
3. Start services with `make up`.
4. Run migrations and create a superuser.
5. Import MITRE ATT&CK data.

## Validation / Expected result
Platform is reachable, admin login works, and core services are running.

## Troubleshooting
For PostgreSQL mount conflicts or bootstrap issues, follow remediation in `Docs/INSTALL_MANUAL.md`.

## Related pages
- [Installation](installation.md)
- [Authentication](../configuration/authentication.md)
- [Backup & Restore](../operations/backup-restore.md)
