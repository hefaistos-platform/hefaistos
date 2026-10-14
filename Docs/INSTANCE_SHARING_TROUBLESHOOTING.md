# Troubleshooting Instance Sharing PULL

PULL runs synchronously in the receiving instance's backend. Expand a row in
**Configuration → Instance Sharing → Pull Job History** to see received,
created, updated, and failed counts for each item type, individual import errors,
request stages with elapsed time, and the origin's export eligibility counts.
Copy the job ID to correlate the UI result with backend logs.

Follow backend logs on the receiving server and, when diagnosing export filters,
on the origin server:

```sh
docker compose logs -f backend
```

Sharing logs use the `organizations.sharing` logger and are enabled at INFO by
default. Set `HEFAISTOS_SHARING_LOG_LEVEL=DEBUG` in the backend environment to
change the log level. API keys and item contents are not logged by the sharing
stage logger. Import failures include exception traces.

Periodic `GET /` requests with user agent `Wget` in frontend/proxy logs are
container health checks. They do not indicate that a PULL fetched any items.
PULL fetches `/api/sharing/info` and `/api/sharing/export` from the origin.
Configure the peer URL to reach the origin's public proxy, which routes `/api/`
to its backend; the standalone frontend container only serves static assets.

An API key authorizes access but does not automatically make every item
exportable. An empty export explains that no eligible items were returned:

- Workbenches must be DEPLOYED and have remote PULL enabled.
- Rules must belong to a DEPLOYED Workbench with remote PULL enabled.
- ACH analyses must be FINISHED and have remote PULL enabled.
- ADVOPS hunts must be DEPLOYED and have remote PULL enabled.
- Capability abstractions must be APPROVED, belong to the origin organization,
  be non-baseline entries, and have remote PULL enabled.
- If the key enforces tag filtering, Workbenches and their rules must match all
  required tags (case-insensitive).
- The key must allow the requested scope; ALL requires authorization for all
  scopes. The configured origin instance UUID must match the responding server.

Origin diagnostics distinguish exclusions by status, disabled sharing, tags,
and deduplication. Upgrade the origin backend as well to receive these counts
and stable source IDs. If older origin responses omit these diagnostics, check
origin eligibility directly. Malformed or incompatible exports produce explicit
errors rather than a successful zero-item import.

Imported objects receive local UUIDs. Workbenches receive local DE IDs and title
prefixes, and ADVOPS hunts receive locally allocated globally unique hunt IDs.
Source mappings identify repeat imports by origin instance, item type, and
source ID, so later pulls update the imported copy while preserving its local
IDs. Older exports without source IDs use source names or hunt IDs for mapping;
renames on those origins may create a new imported copy. Newly imported items
have remote sharing disabled.

Deploy the updated backend and frontend and apply the new database migration:

```sh
docker compose exec backend python manage.py migrate
```

Then repeat PULL and inspect the job details and backend logs. Tests exercise
mocked remote responses; a live pull is still needed to verify the deployed
origin's authentication, TLS, routing, and export settings.
