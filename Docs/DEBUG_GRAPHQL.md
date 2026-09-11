# DEBUG_GRAPHQL.md

GraphQL debugging quick-reference for HEFAISTOS.

This guide provides practical examples for troubleshooting GraphQL authentication, role visibility, query shape errors, and mutation execution.

---

## 1) Access Points

- GraphQL endpoint: `/graphql`
- GraphiQL (if enabled): `/graphql` in browser
- Typical local URL: `https://localhost/graphql`

---

## 2) Authentication

Most queries require a valid JWT access token.

Use header:

```http
Authorization: Bearer <your_jwt_token>
```

Minimal test with `curl`:

```bash
curl -k -X POST https://localhost/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_jwt_token>" \
  -d '{"query":"{ me { id username role } }"}'
```

If you get authentication failures:

- Ensure token is not expired.
- Verify `Authorization` header format is exactly `Bearer <token>`.
- Confirm the user exists and is active.

---

## 3) Sanity Queries

### Current user context

```graphql
query Me {
  me {
    id
    username
    email
    role
  }
}
```

### Basic schema smoke test

```graphql
query IntrospectionPing {
  __typename
}
```

If this fails, check service health and proxy routing before debugging business queries.

---

## 4) Common Debug Workflow

1. Validate endpoint reachability (`/graphql`).
2. Run `IntrospectionPing`.
3. Run `Me` query with token.
4. Execute target query with minimal field set.
5. Add fields incrementally until failure reproduces.
6. Verify role-based access for requested objects/fields.

---

## 5) Typical Error Patterns

### `Cannot query field ... on type ...`

Cause: field name mismatch or outdated client query.

Action:

- Inspect GraphQL schema in GraphiQL/docs.
- Compare field spelling/casing.
- Remove stale fields and retest incrementally.

### `Variable "$x" of required type ... was not provided`

Cause: missing required variable.

Action:

- Confirm variable is present in `variables` JSON.
- Confirm type and nullability match schema.

### `Permission denied` / empty results for non-admin

Cause: RBAC filters or organization/entity scoping.

Action:

- Confirm user `role` via `me` query.
- Re-test with an admin user to isolate RBAC vs data issues.
- Verify organization/entity assignments for user and objects.

---

## 6) Mutation Debugging Template

Use this pattern to isolate mutation issues:

```graphql
mutation ExampleMutation($input: ExampleInput!) {
  exampleMutation(input: $input) {
    ok
    errors
    result {
      id
    }
  }
}
```

Variables:

```json
{
  "input": {
    "name": "debug-test"
  }
}
```

Debug checklist:

- Start with minimum required input fields.
- Validate enum values exactly.
- Confirm referenced IDs exist and are visible to the caller.
- If available, inspect `errors` payload in mutation response before checking server logs.

---

## 7) Useful `curl` Patterns

### Query from shell file

```bash
cat > /tmp/query.json <<'JSON'
{
  "query": "query Me { me { id username role } }"
}
JSON

curl -k -X POST https://localhost/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_jwt_token>" \
  --data @/tmp/query.json
```

### Query with variables

```bash
curl -k -X POST https://localhost/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_jwt_token>" \
  -d '{
    "query": "query Item($id: ID!) { item(id: $id) { id } }",
    "variables": {"id": "1"}
  }'
```

---

## 8) Server-Side Checks (Docker)

```bash
docker compose logs -f backend
```

If needed, open Django shell:

```bash
docker compose exec backend python manage.py shell
```

Recommended checks:

- Confirm user role and active status.
- Confirm object ownership / organization links.
- Confirm migrations are applied.

---

## 9) Notes

- Prefer debugging with production-like RBAC users, not only superusers.
- Keep test queries minimal and add complexity gradually.
- Reuse known-good baseline queries (`me`, `__typename`) to quickly separate infra/auth issues from domain query issues.
