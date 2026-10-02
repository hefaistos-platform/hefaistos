# Authentication

## Purpose
Describe supported authentication modes and recommended secure baseline.

## Audience
Security administrators and platform operators.

## Prerequisites
Configured identity provider details and environment variables.

## Steps / Workflow
1. Choose operating mode (Entra only, Generic OIDC only, mixed, or break-glass hybrid).
2. Configure provider credentials and redirect endpoints.
3. Define user provisioning and role mapping approach.
4. Keep one controlled local break-glass superuser path if required.

## Validation / Expected result
OIDC login works end-to-end and mapped users can access expected roles in HEFAISTOS.

## Troubleshooting
If login fails, verify issuer/audience/JWKS, redirect URIs, and token lifetime assumptions from `Docs/AUTH_SETUP.md`.

## Related pages
- [Security and CORS](security-and-cors.md)
- [User Roles](user-roles.md)
- [GraphQL Debugging](../api/graphql-debugging.md)
