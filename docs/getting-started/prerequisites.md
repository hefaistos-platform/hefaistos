# Prerequisites

## Purpose
Define required runtime stack and tooling before deployment.

## Audience
Operators and engineers preparing a new HEFAISTOS environment.

## Prerequisites
None.

## Steps / Workflow
1. Ensure Docker Engine and Docker Compose plugin are installed.
2. Install Git, OpenSSL, and Python 3.
3. Confirm host resources for database, message broker, search, and app services.
4. Review pinned component versions in `Docs/INSTALL_MANUAL.md`.

## Validation / Expected result
Host is ready to run HEFAISTOS using the documented bootstrap and compose workflows.

## Troubleshooting
If bootstrap fails early, validate Docker daemon status, user permissions, and network egress for image pulls.

## Related pages
- [Quick Start](quick-start.md)
- [Installation](installation.md)
- [Service Matrix](../operations/service-matrix.md)
