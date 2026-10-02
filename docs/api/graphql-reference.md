# GraphQL Reference

## Purpose
Provide a starting map for HEFAISTOS GraphQL endpoint usage.

## Audience
Frontend developers, integrators, and API users.

## Prerequisites
Valid authentication token and network access to `/graphql`.

## Steps / Workflow
1. Authenticate and obtain JWT.
2. Run core queries (current user, workbench listing, rule search).
3. Run key mutations for graph creation, AI generation, and review workflow transitions.

## Validation / Expected result
Authenticated queries and mutations return expected schema-compliant responses.

## Troubleshooting
If operations fail, inspect GraphQL errors for auth, permissions, or query-shape issues.

## Related pages
- [GraphQL Debugging](graphql-debugging.md)
- [User Roles](../configuration/user-roles.md)
- [Detection Workbench](../features/detection-workbench.md)
