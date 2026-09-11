# Detection Chokepoints in HEFAISTOS

This document explains how the Detection Chokepoints feature works in HEFAISTOS, what value it brings, and how to operate it safely.

The current upstream source is:
- `https://github.com/iimp0ster/detection-chokepoints`

HEFAISTOS imports chokepoints, normalizes them into platform data, and uses the active snapshot to ground AI workflows (especially detection engineering prompts).

## Why This Matters

Detection chokepoints improve quality in three ways:

1. Better prioritization
- Chokepoints focus attention on high-value detection anchors per ATT&CK technique.

2. Better implementation speed
- Native hint extraction (`kql`, `spl`, `wazuh_xml`) gives ready-to-adapt query/rule ideas in your target stack.

3. Better consistency in AI output
- The AI layer is grounded against active chokepoint data, reducing generic or context-free suggestions.

## Core Design Principles

1. No auto-apply from upstream
- New upstream content is imported to a `STAGED` snapshot first.
- Nothing becomes active automatically.

2. Explicit approval gate
- You review staged data, then explicitly `Promote to Active`.

3. Fast rollback
- Any archived/previous active snapshot can be promoted again as rollback.

4. Superuser-only control
- Query/mutation access and UI management are restricted to platform superusers.

## Data Model

The backend stores three main entities in `platform_data`:

1. `ChokepointSnapshot`
- Versioned import snapshot.
- Status: `STAGED`, `ACTIVE`, `FAILED`, `ARCHIVED`.
- Tracks source repo/ref/SHA, entry count, summary, validation errors, activation timestamp.

2. `ChokepointEntry`
- Normalized chokepoint row tied to a snapshot.
- Includes ATT&CK mapping (`primary_technique_id`, `sub_technique_id`), telemetry/context, data components, references, tags, confidence, and `native_rule_hints`.

3. `ChokepointImportJob`
- Async import execution record (pending/running/success/failed).
- Stores logs, errors, timing, and linked snapshot.

Also:
- `PlatformDataVersion(framework='detection-chokepoints')` is updated on snapshot activation for version tracking.

## End-to-End Flow

1. Trigger import
- UI path: `/mgmt/framework-updates`
- Mutation: `runChokepointImport`

2. Async execution
- Backend creates/uses a snapshot and runs `import_detection_chokepoints`.

3. Parse + normalize
- YAML files are read and mapped into normalized entries.
- Snapshot summary counters are updated.

4. Stage only
- Successful imports remain `STAGED` until explicitly promoted.

5. Diff review
- `stagedChokepointDiff` compares staged vs active by `entry_key` + `source_hash`.

6. Promote
- `promoteChokepointSnapshot` marks selected snapshot `ACTIVE`.
- Previous active snapshot becomes `ARCHIVED`.

7. Rollback (if needed)
- `rollbackChokepointSnapshot` re-activates a prior snapshot.

## How Parsing Works

The importer is intentionally tolerant to upstream schema variation.

## Accepted sources
- Remote mode: GitHub repo/ref, YAML under `chokepoints/`.
- Local mode: filesystem directory (`--dir`) scanned for `.yml/.yaml`.

## Candidate entry containers
- Top-level list or nested keys like:
  - `chokepoints`
  - `entries`
  - `items`
  - `chokepointentries`
  - `detectionchokepoints`

## Technique and strategy extraction
- ATT&CK IDs from regex: `T####` and `T####.###`
- Detection strategy IDs from regex: `DET###...`

## Native rule hints extraction (Sigma replacement path)
Current extraction buckets:
- `kql`: aliases like `kql`, `kusto`, `sentinel`, `microsoftsentinel`
- `spl`: aliases like `spl`, `splunk`, `splquery`
- `wazuh_xml`: aliases like `wazuh`, `wazuhxml`, `xmlwazuh`

This supports your design direction to prioritize native rule formats over Sigma.

## Snapshot failure behavior
- If import yields zero entries, snapshot is marked `FAILED`.
- Validation warnings and parsing/fetch errors are stored in snapshot/job logs.

## How HEFAISTOS Uses Chokepoints

Active chokepoints are consumed in multiple AI paths:

1. Workbench / rule generation grounding
- AI prompt includes `ACTIVE CHOKEPOINT GUIDANCE` for selected ATT&CK technique.
- Includes telemetry/context and first native hints (`kql`/`spl`/`wazuh_xml`) where available.

2. General AI knowledge grounding
- Keyword-based retrieval can append active chokepoint entries to the grounding block.

3. Maieutic/threat extraction context enrichment
- During extraction, active chokepoint context lines can be appended into technical context metadata.

Practical result:
- The platform can propose more actionable, implementation-ready outputs tied to ATT&CK and operational telemetry.

## UI Usage (Superuser)

Page:
- `/mgmt/framework-updates`

Typical workflow:

1. Check current active snapshot and latest upstream revision.
2. Run `Run Chokepoint Import` (recommended: `REMOTE`, `main`).
3. Review:
- Snapshot summary/validation
- Recent job logs
- Staged diff (`added`, `changed`, `removed`, `unchanged`)
4. Promote staged snapshot when accepted.
5. Roll back if needed.

## API Surface (GraphQL)

Queries:
- `latestAvailableChokepointRevision(sourceRepo, ref)`
- `activeChokepointSnapshot`
- `chokepointSnapshot(id)`
- `chokepointSnapshots(status, limit)`
- `chokepointImportJob(id)`
- `chokepointImportJobs(limit)`
- `stagedChokepointDiff(snapshotId)`

Mutations:
- `runChokepointImport(sourceRepo, ref, mode)`
- `promoteChokepointSnapshot(snapshotId)`
- `rollbackChokepointSnapshot(snapshotId)`

Permissions:
- Superuser required.

## Docker Compose Operations

Use containerized commands only (no host-level `python manage.py` required).

## Migrations
```bash
docker compose exec backend python manage.py migrate
```

## Tests (feature-specific)
```bash
docker compose exec backend python manage.py test platform_data.tests_chokepoints
```

## Manual import command (diagnostics or local dev)
Remote:
```bash
docker compose exec backend python manage.py import_detection_chokepoints \
  --mode remote \
  --source-repo https://github.com/iimp0ster/detection-chokepoints \
  --ref main
```

Local:
```bash
docker compose exec backend python manage.py import_detection_chokepoints \
  --mode local \
  --dir /path/inside/backend/container/to/detection-chokepoints
```

## Important note on `LOCAL` mode from UI
The management command supports `--mode local --dir ...`, but the async job mutation path currently does not pass `--dir`.
Operationally, use `REMOTE` mode in the UI unless local path support is extended in the job runner.

## Upstream Change Strategy

Question: "What happens when upstream changes?"

Answer in current design:

1. Upstream changes are detected by latest ref SHA query.
2. Import creates a new staged snapshot.
3. You review diffs and validation output.
4. You choose whether to promote.
5. You can roll back instantly to prior snapshots.

This makes upstream volatility safe and auditable.

## Benefits for Different User Types

Detection Engineers:
- Faster rule authoring with native hints.
- Better telemetry-aware context per ATT&CK technique.

Threat Hunters / Analysts:
- Higher-quality technical context in playbooks and investigations.

Platform Operators:
- Versioned imports, clear job logs, explicit promotion controls, rollback safety.

AI Consumers (ACH, Workbench, Maieutic Engine):
- Better grounding data, less generic output, more technique-specific guidance.

## Current Limits and Next Improvements

Current limits:
- Local mode is best used via direct management command.
- Upstream schema flexibility is heuristic-based, so unusual YAML structures may degrade extraction quality.

Good future improvements:
- Scheduled refresh jobs with "import-only-to-staged" policy.
- Stronger validation schema and quality scoring before promotion.
- Optional org-scoped overlays/custom chokepoints on top of global snapshot.
- More native hint families (for example EQL, AQL, XQL, Kestrel).

## File Map (Implementation Pointers)

Backend:
- `backend/platform_data/models.py`
- `backend/platform_data/chokepoints_sync.py`
- `backend/platform_data/management/commands/import_detection_chokepoints.py`
- `backend/platform_data/tasks.py`
- `backend/platform_data/schema.py`
- `backend/platform_data/tests_chokepoints.py`

AI integration:
- `backend/ai_assistant/engine.py`
- `backend/ai_assistant/schema.py`

Frontend:
- `frontend/src/pages/FrameworkUpdatesPage.tsx`

