# GraphQL Debugging

## Purpose
Provide troubleshooting flow for GraphQL access, authentication, and schema/query errors.

## Audience
Developers and operators diagnosing API issues.

## Prerequisites
Access to request tooling and backend/container logs.

## Steps / Workflow
1. Verify endpoint reachability and auth headers.
2. Run sanity queries to confirm schema responsiveness.
3. Diagnose common query/mutation errors and variable mismatches.
4. Correlate failures with container/service logs.

## Validation / Expected result
You can identify whether issues are auth, query-shape, role visibility, or backend health related.

## Troubleshooting
Use `Docs/DEBUG_GRAPHQL.md` cURL patterns and error examples for rapid triage.

## Related pages
- [GraphQL Reference](graphql-reference.md)
- [Authentication](../configuration/authentication.md)
- [Service Matrix](../operations/service-matrix.md)
