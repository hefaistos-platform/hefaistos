# In-App System Update (Superuser Only)

HEFAISTOS now supports a system-wide in-app update workflow from Configuration → **System Update**.

## Security model

- Only Django `is_superuser` accounts can access update check/start/status/log endpoints.
- Organization admin roles are not sufficient.
- Update attempts are audit-logged with actor, mode, time, and outcome.

## Command sequences

Default mode (lower downtime):

1. `docker compose pull`
2. `docker compose --profile batch run --rm migrate`
3. `docker compose --profile workers --profile obs --profile devtools up -d --build --remove-orphans`

Force mode (recovery; downtime expected):

1. `docker compose down --remove-orphans`
2. `docker compose pull`
3. `docker compose --profile workers --profile obs --profile devtools up -d --build --remove-orphans`
4. `docker compose --profile batch run --rm migrate`

## Runtime behavior and safety

- Jobs run asynchronously in background threads.
- Single-flight lock is enforced; concurrent start attempts return `409 Conflict`.
- Step logs are captured and returned via job log API.
- Basic secret redaction is applied to logged command output.
- Per-step and overall job timeouts are enforced.
- Final readiness check runs `docker compose ps --services --filter status=running` and fails the job if no services are reported running.
- Update check response includes both installed local version and repository version from git origin (default branch `VERSION` file) so operators can clearly see what is running versus what is available.

## API endpoints

- `GET /api/system/config/update/check`
- `POST /api/system/config/update/start` (body: `{ "force": true|false }`)
- `GET /api/system/config/update/jobs/{job_id}`
- `GET /api/system/config/update/jobs/{job_id}/logs?start=0&limit=500`

`GET /api/system/config/update/check` returns:

- `local_version`: installed version on this instance.
- `current_version`: legacy alias of `local_version` for backward compatibility.
- `repository.version`: version read from repository origin default branch `VERSION`.
- `update_available`: `true` when repository version is newer, `false` when same/older, `null` when versions cannot be compared.

### Ownership/safe.directory note

In some containerized deployments, git can refuse repository access with a "dubious ownership" error. The backend now retries git lookups with a scoped `safe.directory` override for the detected repository path. If repository version is still unavailable, set `HEFAISTOS_REPOSITORY_VERSION` to provide an explicit remote version value.

All endpoints require authenticated superuser access.
