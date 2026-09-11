# Waiting Room Workbench: Feature Guide

## What the Waiting Room Is

The **Waiting Room** is HEFAISTOS’s controlled intake area for external detection intelligence before it becomes part of operational content in a Workbench.

In practice, it is a review queue where incoming cases are collected, normalized, triaged, and either promoted to a Workbench or ignored/left pending. This separation protects production content from noisy or low-quality input and gives analysts and reviewers an auditable approval step.

The Waiting Room is primarily used to:

- Ingest candidate detection ideas from integrations (for example, MISP).
- Preserve imported context and metadata in a consistent internal model.
- Let reviewers and analysts inspect and validate content before promotion.
- Prevent duplicate imports and avoid accidental re-processing.
- Track lifecycle state of candidates from intake to promotion.

---

## Why It Exists

Detection engineering pipelines often consume high-volume external intelligence. Directly writing that data into active Workbenches can create operational risk:

- irrelevant events,
- duplicated entries,
- inconsistent metadata,
- and unreviewed low-confidence content.

The Waiting Room addresses this by introducing a **staging + governance layer**:

1. **Stage** incoming cases safely.
2. **Review** and enrich them as needed.
3. **Promote** only approved cases to Workbench.

This pattern keeps the system reliable while still enabling fast import workflows.

---

## Core Domain Concepts

### Waiting Case

A **WaitingCase** is a normalized internal record representing a candidate item under review.

Typical characteristics:

- Has its own UUID and lifecycle status.
- May carry source linkage (for example, MISP instance/event identifiers).
- Contains the metadata needed for review and eventual promotion.

### Workbench

A **Workbench** is the downstream operational object (typed in GraphQL as `PlaybookGraphType`) where approved detection content is managed.

Promotion from Waiting Room to Workbench is explicit and role-gated.

### Source Deduplication

The import flow prevents creating multiple waiting cases for the same source event within the same integration scope (for example, same `misp_event_id` + instance).

---

## End-to-End Flow

1. **Import** candidate cases (manually or via MISP integration).
2. **Normalize** source payloads into internal WaitingCase-ready structures.
3. **Filter** based on optional import constraints (for example, tag gating).
4. **Deduplicate** existing source events.
5. **Create** new waiting cases for eligible events.
6. **Review/Update** cases in Waiting Room.
7. **Promote** approved case to Workbench.

At each step, counts and statuses provide traceability of what was imported, skipped, and promoted.

---

## GraphQL Surface (Waiting Room)

## Mutations

### `createWaitingCase`

Creates a waiting case directly.

**Required role:** `REVIEWER` or `ADMIN`

### `updateWaitingCase`

Updates an existing waiting case’s reviewable data/state.

**Required role:** `REVIEWER` or `ADMIN`

### `importWaitingCasesFromMisp`

Imports waiting cases from a configured MISP instance, with optional event and tag filtering.

**Required role:** `REVIEWER` or `ADMIN`

### `promoteWaitingCaseToWorkbench`

Promotes an approved waiting case into a Workbench object.

**Required role:** `ANALYST`

---

## Promotion to Workbench

The promotion mutation returns a result object containing operation status and promoted object references.

### Response Semantics

`promoteWaitingCaseToWorkbench` returns:

| Field | Type | Status |
|-------|------|--------|
| `workbench` | `PlaybookGraphType` | **Primary field** for all current/future clients |
| `graph` | `PlaybookGraphType` | **Deprecated alias** for backward compatibility |

Both fields resolve to the same underlying Workbench object.

- Prefer `workbench` in all new code.
- `graph` remains temporarily to avoid breaking older clients.
- Deprecation reason in schema: `Use workbench field instead. graph will be removed in a future release.`

### Example

```graphql
mutation PromoteCase($id: UUID!) {
  promoteWaitingCaseToWorkbench(id: $id) {
    success
    message
    waitingCase { id status }
    workbench { id title }
    graph { id title }   # deprecated alias
  }
}
```

---

## Ingestion Model: MISP-Only, No Direct API Push

**HEFAISTOS never accepts a direct API push of a Waiting Room case from another
tool.** The only intake path is `importWaitingCasesFromMisp`, which PULLS from a
configured MISP instance. There is no `/api/waiting-room/cases` REST endpoint —
that direct-push path (previously documented in `PARTNER_INTEGRATION_GUIDE.md` /
`PARTNER_INTEGRATION_QUICKSTART.md`) was retired in favor of this model.

Other tools that want to land content in the Waiting Room must:

1. Build a MISP event carrying a structured MISP Object (e.g. the
   `capability-abstraction` object — see
   `/Volumes/Data/Scripts/dragonnews-misp/misp-objects/capability-abstraction/`).
2. Tag the event `HEFAISTOS`.
3. Either push it directly to a MISP instance the target HEFAISTOS org has
   configured, or commit it to a Git repo consumed by such an instance.
4. HEFAISTOS pulls it in via `importWaitingCasesFromMisp` (manually, or on the
   `auto_pull_enabled` schedule configured on the `MISPInstance`).

`normalize_misp_event()` in `waiting_room/misp.py` is Object-aware: if an event
carries a `capability-abstraction` MISP Object, its attributes (`title`,
`short-description`, `detection-objective`, `attack-technique-id`, etc.) are
mapped directly onto WaitingCase fields; otherwise it falls back to the older
flat-attribute/Tag/Galaxy heuristic.

## Import Ledger: Permanent, Survives Deletion

`MISPImportLedger` records every `(misp_instance, misp_event_id)` pair ever
imported, independent of the `WaitingCase` row's own lifecycle. If a reviewer
deletes a WaitingCase from the Waiting Room (`deleteWaitingCase`), the ledger
entry survives — a later `importWaitingCasesFromMisp` run will never recreate a
case for that same MISP event. This is deliberate: rejection in the Waiting Room
is a permanent decision, not a cache that clears itself on the next pull.

There is currently no mutation to remove a ledger entry (i.e. no "un-reject, let
me re-import this event" action) — that is a deliberate absence, not an
oversight, pending a real need to reverse a rejection.

## Scheduled Auto-Pull

`MISPInstance` carries `auto_pull_enabled`, `auto_pull_schedule`
(`HOURLY`/`DAILY`/`WEEKLY`), `auto_pull_tag` (defaults to `HEFAISTOS`), and
`next_auto_pull_at`. When enabled, `run_scheduled_misp_pulls` (management
command, wired into `run_scheduler.py`) periodically calls the same
`import_waiting_cases_from_misp()` function the GraphQL mutation uses, acting as
an org ADMIN (or the first available user if no admin exists). Configure via
`createMISPInstance`/`updateMISPInstance`.

## MISP Import: Behavior and Tag Gating

The Waiting Room supports MISP intake through `importWaitingCasesFromMisp`.

### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `mispInstanceId` | `UUID!` | Yes | MISP instance UUID |
| `eventId` | `String` | No | Import one specific MISP event |
| `tag` | `String` | No | Import only events carrying this tag |
| `limit` | `Int` | No | Max events fetched (default: `25`) |
| `runAiEnrichment` | `Boolean` | No | Queue AI enrichment for imported cases (default: `false`) |

### Import Processing Rules

When `tag` is provided and non-empty:

1. Events are fetched as usual (respecting `eventId` and `limit`).
2. Tag matching is enforced during normalization and again before persistence.
3. Events without the required tag are skipped (not created).
4. Duplicate events (already imported for the same instance) are skipped.

When `tag` is omitted/empty:

- All fetched events are eligible (subject to existing validation/deduplication).

### Response Contract

| Field | Type | Meaning |
|-------|------|---------|
| `success` | `Boolean` | Operation completed without error |
| `message` | `String` | Human-readable import summary |
| `importedCount` | `Int` | Number of new waiting cases created |
| `skippedCount` | `Int` | Number skipped (tag mismatch, duplicate, or missing ID) |
| `waitingCases` | `[WaitingCaseType]` | Newly created waiting cases |

### Example Mutation

```graphql
mutation ImportWaitingCasesFromMisp($mispInstanceId: UUID!, $tag: String) {
  importWaitingCasesFromMisp(mispInstanceId: $mispInstanceId, tag: $tag) {
    success
    message
    importedCount
    skippedCount
    waitingCases {
      id
      title
      status
    }
  }
}
```

**With tag filter**

```json
{
  "mispInstanceId": "550e8400-e29b-41d4-a716-446655440000",
  "tag": "HEFAISTOS"
}
```

**Without tag filter**

```json
{
  "mispInstanceId": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## Frontend Behavior

The Waiting Room import and promotion UX is aligned to the API contract:

- MISP import modal includes **Required tag (optional)**.
- If entered, UI sends `tag` in import mutation variables.
- Post-promotion flows should consume `workbench` as canonical response field.
- Existing consumers of `graph` continue to work during deprecation window.

---

## Security and Authorization Model

Waiting Room operations are role-gated to preserve review discipline:

| Operation | Required Role |
|----------|----------------|
| `createWaitingCase` | `REVIEWER`, `ADMIN` |
| `updateWaitingCase` | `REVIEWER`, `ADMIN` |
| `importWaitingCasesFromMisp` | `REVIEWER`, `ADMIN` |
| `promoteWaitingCaseToWorkbench` | `ANALYST` |

Recommended practice is least privilege: grant promotion rights only to analyst roles that own final approval.

---

## Operational Notes and Best Practices

- Prefer bounded imports (`limit`) for predictable review batches.
- Use `tag` to scope imports to campaign- or program-relevant intelligence.
- Monitor `importedCount` vs `skippedCount` to quickly detect noisy feeds.
- Standardize on `workbench` in GraphQL clients now to avoid future breakage.
- Keep Waiting Room review states current so promotion queues remain actionable.

---

## Backward Compatibility and Migration Guidance

### Promotion response migration

- Legacy clients reading `graph` continue to function.
- Migrate query documents to `workbench` as soon as possible.

### MISP import callers

- Existing calls without `tag` remain valid and preserve prior behavior.
- New callers can optionally add `tag` to enforce import hygiene.

### Count fields across versions

- `importedCount` and `skippedCount` may not exist on older backend versions.
- If supporting mixed deployments, guard field selection or version-pin API usage.

---

## Summary

The Waiting Room is HEFAISTOS’s controlled intake and approval layer for detection content. It enables safe ingestion, deterministic filtering, duplicate prevention, and role-gated promotion into Workbench. With tag-gated MISP import and explicit `workbench` promotion semantics, teams can scale intake while maintaining quality and governance.
