# Telemetry Tagging (Milestone 1)

This document explains the Telemetry Tagging feature in HEFAISTOS: what it is, why it
exists, how it works end to end, and — just as important — what it deliberately does
**not** do yet.

## What This Is

Telemetry Tagging is an AI-assisted enrichment step on a Workbench object
(`PlaybookGraph`) that derives a list of the telemetry a detection is expected to
depend on — sources, MITRE data components, and specific field names — **after** the
analyst has already completed the behavior-first engineering work (technique
selection, strategic goal, technical context, the detection rule itself, and threat
surface taxonomy).

It produces an editable, reviewable tag list attached to the Workbench object. That
list travels with the detection into Rule Hub and downstream exports, so anyone
consuming the detection (a SIEM team, a reviewer, a future maintainer) can see exactly
what telemetry the author believed the rule needed — without reverse-engineering it
from the query body or chasing the original author down.

## Why This Exists

Detection-engineering cycle time is dominated less by writing the rule than by finding
accessible telemetry, confirming data quality, validating logic against realistic
behavior, and going back and forth with the SIEM/data team about "why isn't this
firing." A large share of that back-and-forth exists because the telemetry a detection
depends on is usually implicit — buried in a query string or in the original author's
head — rather than an explicit, reviewable artifact attached to the detection object.

**Design stance (important, and different from a common industry pattern):**
Telemetry Tagging does **not** ask analysts to start from "what event ID / log source
do we have" and work backward into a rule. That produces detections anchored to
whatever telemetry happens to be convenient, which is fragile and easy for an
adversary to evade by changing the artifact. Instead, HEFAISTOS keeps behavior-first
authoring as the required starting point (technique, procedure narrative, blind
spots, OpenTIDE attributes, the rule logic) and derives the telemetry requirement
**from** that completed analysis, as a byproduct — never as a precondition for
starting to think.

## Hard Gate: Required Fields Before Derivation Can Run

Telemetry-tag derivation is **hard-blocked** until all five of the following fields
are populated on the Workbench object:

| # | Field | Workbench location | Model field |
|---|---|---|---|
| 1 | ATT&CK TTP | Part 1 — Detection Strategy | `mitre_technique` |
| 2 | Strategic Goal | Part 2 — Deep Dive | `goal` |
| 3 | Technical Context | Part 2 — Deep Dive | `technical_context` |
| 4 | Detection Rule | Part 3 — Detection Rules | `detection_rule` |
| 5 | Threat Surface Taxonomy | Part 4 — SOAR Configuration | `threat_surface` |

**Why these five and not more/fewer:** this is exactly the set of fields that make
technique-derivation and narrative-extraction meaningful. ATT&CK TTP is the primary
lookup key against MITRE reference data. Technical Context is the free text mined for
tool/artifact-specific telemetry that technique-mapping alone would miss. Threat
Surface Taxonomy narrows candidates by platform (Windows vs. Azure produce very
different telemetry vocabulary for the same technique). Strategic Goal constrains
scope/intent. Detection Rule gives the derivation step actual logic to cross-check
claimed telemetry against — catching mismatches between what the rule queries and what
the narrative claims it needs, essentially free internal-consistency QA.

**Important exception, stated explicitly:** Part 4 (SOAR Configuration) is documented
elsewhere in the HEFAISTOS KB as a genuinely optional Workbench section. This feature
promotes exactly one field inside that otherwise-optional section — `threat_surface`
— into a hard precondition for telemetry-tag derivation, while the rest of Part 4
remains optional. Frontend implementations must ensure `threat_surface` is reachable
and fillable even when the analyst's Part 4 visibility is collapsed/hidden by the
system→org→user→local workbench visibility policy — otherwise the gate can silently
block with no way for the analyst to see why.

**Gate enforcement is server-side, not just UI:** the gate is checked twice —
`PlaybookGraph.telemetry_tagging_missing_fields()` / `telemetry_tagging_gate_passed()`
on the model, and again inside the `deriveTelemetryRequirements` GraphQL mutation
before any AI call is made. A UI can (and should) disable the trigger button and show
missing fields via a tooltip, but the backend never trusts that check alone.

## What Gets Derived, and From What Sources

When the gate passes and derivation runs, the process pulls candidates from data
**already present in HEFAISTOS** — no new import job or external scrape is needed:

1. **`MitreDataComponent`** linked to the selected ATT&CK technique — MITRE's generic
   technique-to-data-component mapping.
2. **`ChokepointEntry`** from the currently *active* chokepoints snapshot, matched by
   technique/sub-technique ID — carries `telemetry_prerequisites`, `data_components`,
   `native_rule_hints`, and `platforms` where available.
3. **`DataSourceField`** (from `data_catalog`) matching the data sources implied by
   step 1 — used purely as **field-name terminology/vocabulary**, so suggestions are
   phrased in concrete field-like terms instead of vague category names.
4. **Free-text extraction** over `technical_context`, to catch tool- or
   artifact-specific telemetry the technique mapping alone wouldn't surface.
5. **Cross-check against the `detection_rule` body**, to flag telemetry the rule
   clearly queries but the candidate list missed, or drop candidates the rule clearly
   doesn't use.

All of this is assembled into a prompt and sent through the existing AI provider
abstraction (`ai_assistant/opentide_enrichment.call_ai_provider`), following the same
provider-resolution/settings pattern used by OpenTIDE metadata enrichment elsewhere in
HEFAISTOS.

## CRITICAL: What "Unverified" Means Here

**`DataSourceField` / `DataSource` in the current HEFAISTOS data model are populated by
a bulk MITRE scrape (`data_catalog.tasks.run_mitre_deep_import_job`), not by any
connection to an organization's actual SIEM or log platform.** They represent what
MITRE documents as available data sources/fields for ATT&CK analytics — a reference
vocabulary — not a verified inventory of what a specific organization ingests, or
whether that ingestion is healthy.

Because of this, **every entry produced by Telemetry Tagging is stamped
`status: "unverified"`, unconditionally, in this milestone.** There is currently no
mechanism in HEFAISTOS that checks a derived telemetry requirement against a real
SIEM/data platform. Treating this list as proof that the required telemetry actually
exists and is healthy in your environment would repeat exactly the mistake HEFAISTOS's
own documentation already warns against for Rule Hub ("rule exists in the library" ≠
"detection is complete/deployed/operationally proven"). The same discipline applies
here: "telemetry requirement is documented" ≠ "telemetry requirement is confirmed
present."

A future milestone may add an org-environment health/verification layer (e.g. a live
connector that checks field presence/freshness against the actual SIEM, or a manual
attestation workflow where the SIEM team marks catalog entries as confirmed). This
milestone intentionally does not build that layer, and does not pretend it exists.

## Output Schema

Stored on `PlaybookGraph.telemetry_requirements` (`JSONField`, default `[]`), following
the same "list of small structured dicts" pattern already used elsewhere in the model
(`enrichment_steps`, `containment_steps`, `notification_steps`):

```json
[
  {
    "id": "9f2b...uuid",
    "source": "Windows Security Event Log",
    "component": "Process Creation",
    "fields": ["NewProcessName", "ParentProcessName", "CommandLine"],
    "rationale": "Derived from T1059.001 procedure narrative and cross-checked against the rule body.",
    "origin": "ai_derived",
    "status": "unverified"
  }
]
```

- `origin`: `"ai_derived"` for entries produced by the derivation pass, `"manual"` for
  entries an analyst adds/edits directly.
- `status`: always `"unverified"` in this milestone. The `updateTelemetryRequirements`
  mutation forcibly resets this field on save so a client cannot claim a verified
  status that HEFAISTOS has no way to back up.

`PlaybookGraph.telemetry_requirements_generated_at` records the timestamp of the last
successful derivation run, so the UI can show staleness (e.g. "derived 3 edits ago,
consider re-running").

## GraphQL API

### Mutation: `deriveTelemetryRequirements(id: UUID!)`

Runs the derivation pass for the given Workbench (`PlaybookGraph`) ID.

- If the required-field gate fails, returns `ok: false` and `missingFields: [...]`
  with no AI call made and no change to the stored list.
- If the gate passes, runs derivation, persists the result to
  `telemetry_requirements` (overwriting the previous derived list — analysts should
  review/edit and save via `updateTelemetryRequirements` if they want to keep manual
  additions across re-runs), and returns `ok: true` with the new list.
- Requires `ADMIN`, `ANALYST`, or `REVIEWER` role and org-scoped ownership of the
  Workbench, same authorization pattern as other Workbench mutations.

### Mutation: `updateTelemetryRequirements(id: UUID!, telemetryRequirements: JSONString!)`

Persists an analyst-edited/curated telemetry requirement list — used after reviewing
an AI-derived draft, or for fully manual entries. Does not re-run derivation or
re-check the five-field gate (curating an existing or hand-authored list is always
allowed). Always forces `status: "unverified"` on every entry regardless of what the
client sends, since no verification layer exists yet.

### Query fields on `PlaybookGraphType`

- `telemetryRequirements: JSONString`
- `telemetryRequirementsGeneratedAt: DateTime`
- `telemetryTaggingMissingFields: [String]` — convenience resolver so the frontend can
  render the gate state (which fields are still missing) without duplicating the gate
  logic client-side.

## Non-Goals (Explicitly Out of Scope for This Milestone)

- **No organization-environment verification.** Nothing here checks whether a data
  source/field actually exists, is populated, or is healthy in a specific org's SIEM.
- **No health/freshness checks or live SIEM connector.**
- **No gating of rule authoring, review, or deployment** on the presence or
  completeness of `telemetry_requirements`. The five-field gate governs only whether
  the *derivation button* can run — it does not block saving, submitting for review,
  or deploying a Workbench object that has no telemetry tags at all.
- **No claim that `DataSourceField` represents organizational reality.** It is treated
  throughout this feature strictly as MITRE reference vocabulary.

These are correctly deferred to a future milestone, once/if HEFAISTOS builds an actual
org-environment telemetry-health layer.

## File Map (Implementation Pointers)

Backend:
- `backend/playbooks/models.py` — `PlaybookGraph.telemetry_requirements`,
  `telemetry_requirements_generated_at`, `telemetry_tagging_missing_fields()`,
  `telemetry_tagging_gate_passed()`.
- `backend/playbooks/migrations/0048_telemetry_tagging.py` — adds the two new fields.
- `backend/ai_assistant/telemetry_derivation.py` — reference-data collection, prompt
  construction, AI call, output cleaning (`derive_telemetry_requirements`,
  `TelemetryGateError`).
- `backend/playbooks/schema.py` — `PlaybookGraphType` fields/resolver,
  `DeriveTelemetryRequirements` mutation, `UpdateTelemetryRequirements` mutation,
  registered on the root `Mutation` type.

Reference data consumed (no changes made to these):
- `backend/platform_data/models.py` — `MitreDataComponent`, `ChokepointEntry`,
  `ChokepointSnapshot`.
- `backend/data_catalog/models.py` — `DataSource`, `DataSourceField`.

Related HEFAISTOS docs:
- `Docs/README_CHOKEPOINTS.md` — the chokepoints dataset consumed as one of the
  reference-candidate sources here.

## Good Future Improvements

- Org-environment telemetry-health verification layer (its own milestone; see
  "Non-Goals" above).
- Surfacing `telemetry_requirements` directly in the OpenTIDE MDR/DOM export so it
  travels automatically into published detection artifacts, not just the Rule
  Hub/Workbench UI.
- A "stale telemetry tags" indicator when `technical_context`, `detection_rule`, or
  `mitre_technique` change materially after the last `telemetry_requirements_generated_at`.
- Extending the consistency cross-check (derived tags vs. rule body) into a scored
  confidence value per entry, rather than a binary include/exclude decision.
