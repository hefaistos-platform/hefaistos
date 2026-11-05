# Maieutic Engine 3.0: Detection Specification

Status: **DESIGN, in progress (branch `feat/maieutic-3`)**. Not implemented yet.
`Docs/README_MAIEUTIC.md` still describes the current engine until Phase 7.
Based on HEFAISTOS v1.9.20 (`c9af8fe6`) and ADE commit `228098f`.

Field names below were verified against `backend/playbooks/models.py` in Phase 1.
Items still marked **[VERIFY]** are unresolved.

## 1. Purpose

The Detection Specification (the "spec") is the single structured record of everything the
user decided during a Maieutic session. It is the only input to:

1. Workbench creation (fills workbench fields).
2. Rule generation (one task per selected format).
3. The spec-traceability table (did each decision reach the rule?).
4. A future "check an existing rule against ADE" feature (reads the same ledger).

It is stored on a `MaieuticDraft` (section 9), then copied onto the created workbench.

## 2. The item envelope

Every user-facing value is wrapped so origin is never lost.

```
Item<T> = {
  value:               T | null,
  origin:              "STATED" | "CONFIRMED" | "UNKNOWN",
  suggestion:          T | null,      // what the AI proposed, if anything
  edited_suggestion:   boolean,       // user rewrote the suggestion
  help_rungs_used:     [1,2,3],       // hint ladder steps pressed
  updated_at:          ISO-8601
}
```

- `STATED`: typed by the user with no AI proposal.
- `CONFIRMED`: AI proposed, user accepted or rewrote it (hybrid rule).
- `UNKNOWN`: user chose "I don't know yet". `value` is null.

**Rule: for ADE questions `suggestion` is always null.** The AI never proposes ADE answers.
The only AI-proposed values anywhere are: the STP suggestion, and optional wording help on
non-ADE fields.

## 3. Top-level structure

```
spec = {
  meta, hypothesis, interrogation, design, robustness, playbook_tests, review
}
```

### 3.1 meta

| Field | Type | Notes |
|---|---|---|
| spec_version | int | Starts at 1. Bumped when this schema changes |
| engine_version | string | HEFAISTOS version that wrote it |
| draft_id | uuid | `MaieuticDraft.id` |
| challenge_level | LIGHT / STANDARD / EXPERT | Controls which ADE questions apply and how open help is |
| framework_refs | object | `{ attack, chokepoints, ade_snapshot_id, ade_overlay_version }` captured at start and updated on each ADE answer |
| tlp | string | Same `TLP_CHOICES` as `PlaybookGraph` and `MveDraft` (`playbooks.utils.tlp`) |
| current_stage | 1..6 | For resume |

### 3.2 hypothesis (stage 1)

| Field | Type | Required to create workbench |
|---|---|---|
| title | Item<string> | yes |
| technique | `{ id, name, sub_id, status }` where status is SET or NONE_CHOSEN | yes (NONE_CHOSEN is an explicit allowed choice) |
| goal | Item<string> | yes |
| attacker_methods | list of Item<string> | no, recommended |
| scope_notes | Item<string> | no |

`attacker_methods` is the in-scope list ADE2 needs. Each entry is one way an attacker can
achieve the behaviour.

### 3.3 interrogation (stage 2)

| Field | Type | Notes |
|---|---|---|
| log_sources | list of `{ kind: LOG_SOURCE / DATA_SOURCE / FREE_TEXT, ref_id, name, coverage_status_at_pick }` | Dropdown from Log Source first, Data Source second. `coverage_status_at_pick` is ACTIVE / PARTIAL / MISSING at selection time |
| fields | list of `{ standard_name, siem_field_name, attacker_controlled: YES / PARTIAL / NO / UNKNOWN, note }` | `attacker_controlled` feeds ADE1 and the STP derivation |
| benign_lookalikes | list of Item<string> | Feeds `false_positives` |
| qa_log | list of `{ question, answer, stage, at }` | Non-ADE Socratic Q&A |

### 3.4 design (stage 3): the blueprint in words

| Field | Type | Notes |
|---|---|---|
| match_elements | list of `{ id, description, anchor_type, field_ref, attacker_changeable }` | `anchor_type`: FILE_OR_PROCESS_NAME, COMMAND_LINE_TEXT, REGISTRY, API_OR_SYSCALL, NETWORK, IDENTITY, OTHER. `attacker_changeable`: FREELY / WITH_EFFORT / NO / UNKNOWN |
| exclusions | list of `{ what, why }` | Feeds `false_positives` and ADE4 |
| windows_thresholds | `{ time_window, alert_threshold, threshold_operator, aggregation_field, aggregation_function, suppression_window }` | Names match the `PlaybookGraph` tuning fields. `alert_threshold` is an integer, the rest strings |
| correlations | list of Item<string> | |
| focus_layer | enum | Maps to `detection_focus_layer` |
| capability_refs | list of capability ids | Dropdown, shown only when technique is SET |
| blueprint_text | Item<string> | The design in plain language, shown back to the user |

`match_elements` is what the ADE planner reads. The planner works on this structure and
the technique, not on rule syntax, so it works for every format.

### 3.5 robustness (stage 4)

**STP block**

```
stp = {
  beginner_answers: { anchor_type, attacker_changeable, telemetry_origin },
  claimed:   { level: 1..5 | null, column: "A"|"U"|"K"|"P"|"H"|null, reason },
  evidence_supported: { level, column, derivation: [ { ade_id, effect } ] },
  ai_suggestion: { level, column, reasoning, cited_ade_ids },
  final:     { level, column },
  override_reason: string | null
}
```

Order: claimed first, then evidence, then AI suggestion, then final. `final` is always the
user's decision. `override_reason` is required when final is higher than evidence_supported.
`column` goes to the workbench `data_source_robustness` (A/U/K/P/H), not `dataSourceMaturity`.

**ADE ledger**

```
ade_ledger = [ {
  ade_id:            "ADE3-01",
  snapshot_id:       uuid,          // upstream snapshot answered against
  overlay_version:   int,           // our question/hint version
  question_id:       string,
  trigger_reason:    "design" | "match_element:<id>" | "technique" | "expert_all",
  question_text:     string,        // rendered text the user saw
  answer_text:       string,        // typed by the user
  disposition:       enum,
  design_ref:        string | null, // match_element id, exclusion id ...
  help_rungs_used:   [1,2,3],
  evaluator_flag:    "ANSWERED" | "VAGUE" | "CONTRADICTS_DESIGN" | null,
  answered_at:       ISO-8601
} ]
```

`disposition` values:

| Value | Meaning | Group sent to generator |
|---|---|---|
| HANDLED_IN_DESIGN | The design already deals with it, or was edited to | must_handle |
| ACCEPTED_LIMITATION | Known gap, will not be covered here | accepted_limitations |
| COVERED_BY_OTHER_RULE | Another rule handles it (reference required) | accepted_limitations, with the reference |
| NOT_APPLICABLE | Does not apply (reason required) | none |
| UNKNOWN | User does not know yet | accepted_limitations, flagged unknown, and added to blind_spots |

A question with no disposition is **open**. The evaluator flag is advisory and never blocks.

### 3.6 playbook_tests (stage 5)

| Field | Type |
|---|---|
| triage_guidance, response_playbook | Item<string> |
| downstream_correlation_requirements | Item<object>, from `design.correlations` |
| enrichment_steps, containment_steps, notification_steps | Lists as on `PlaybookGraph` (`{action,input,output,description}`, `{action,critical,description}`, `{channel,recipient,template}`) |
| alert_trigger (text), default_severity (LOW / MEDIUM / HIGH / CRITICAL) | Item<string>; severity must be one of the four enum values |
| test_scenario, test_expected_output | Item<string> |
| negative_tests | list of `{ from_ade_id, idea }`, one per ACCEPTED_LIMITATION or UNKNOWN |

### 3.7 review (stage 6)

| Field | Type |
|---|---|
| output_formats | list, KQL always first and locked. Others from SPL, EQL, WAZUH, AQL |
| exit | CREATE_AND_GENERATE / CREATE_WITHOUT_RULE / SAVE_DRAFT |
| completeness | derived, see section 6 |

## 4. Derived constraint groups (computed at generation time)

Computed by code and frozen into the generation task input. Not typed by the user.

- **must_implement**: `hypothesis`, `match_elements`, `exclusions`, `windows_thresholds`,
  `correlations`, selected capability entries, chosen log source and field mappings.
- **must_handle**: ADE entries with disposition HANDLED_IN_DESIGN, each with its design reference.
- **accepted_limitations**: ACCEPTED_LIMITATION, COVERED_BY_OTHER_RULE and UNKNOWN entries.

The generator prompt must treat the groups differently: implement, handle or avoid, and do not
pretend to cover.

## 5. ADE to STP rules (PROPOSAL, requires human review)

The evidence-supported level is computed from confirmed gaps. This table is my own proposal
for HEFAISTOS's 1-5 plus A/U/K/P/H model. **I did not check it against MITRE's published
Summiting the Pyramid scoring.** It may need to change.

| Confirmed ADE gap | Effect |
|---|---|
| ADE1-01, ADE1-02 (mutable strings) | Anchor treated as level 1-2; claims of 3+ contradicted |
| ADE3-01 (identity by name) | Level capped at 2 unless a second non-name anchor exists |
| ADE3-05 (trusting parent lineage) | Level capped at 2, column cannot exceed K for the lineage element |
| ADE2-01 to ADE2-04 (omitted alternatives) | A "5" claim drops to 4 |
| ADE4-04 (field missing or mismapped) | Affects column and telemetry requirements, not level |
| ADE3-02, ADE3-03, ADE3-06, ADE4-01 to ADE4-03 | No level effect; reported as logic-reliability status |

Titles for IDs not named above come from the imported ADE snapshot. This draft does not copy
them from memory.

## 6. Completeness meter (derived, not a quality score)

Reported as counts:

- items: stated / confirmed / unknown across required and recommended fields
- ADE: answered / applicable (applicable depends on challenge level and the planner)
- STP: claimed set? evidence derived? final set?
- formats: for each selected format, "validated" or "not validated"

There is no single percentage. A number would imply rule quality, which this does not
measure. It measures how much of the user's thinking was captured.

## 7. Minimum set to create a workbench

`hypothesis.title`, `hypothesis.technique` (SET or NONE_CHOSEN), `hypothesis.goal`.
Everything else may be UNKNOWN. SAVE_DRAFT has no minimum.

## 8. Spec to workbench mapping

| Workbench field | Source in spec |
|---|---|
| title | hypothesis.title |
| mitre_technique | hypothesis.technique |
| goal | hypothesis.goal + attacker_methods |
| technical_context | interrogation + design.blueprint_text |
| false_positives | benign_lookalikes + exclusions |
| blind_spots | accepted_limitations + UNKNOWN items |
| triage_guidance, response_playbook, alert_trigger, default_severity, enrichment/containment/notification steps | playbook_tests |
| time_window, alert_threshold, threshold_operator, aggregation_field, aggregation_function, suppression_window | design.windows_thresholds |
| downstream_correlation_requirements | design.correlations |
| telemetry_requirements | interrogation.log_sources (status stays `unverified`, as in `Docs/TELEMETRY_TAGGING.md`) |
| detection_rule + detection_rule_format | primary KQL result |
| opentide_yaml + configured_platforms | additional formats (section 9a) |
| test_scenario, test_expected_output | playbook_tests incl. negative_tests |
| robustness_level | robustness.stp.final.level |
| data_source_robustness | robustness.stp.final.column |
| detection_focus_layer | design.focus_layer |
| selected_capability_abstractions | design.capability_refs |
| conversation_history | full session transcript (collapsible in UI) |
| new: maieutic spec + ledger | whole spec, read-only |

Verified in Phase 1: all workbench field names in this table exist on `PlaybookGraph`.

## 9. Persistence: MaieuticDraft (modelled on MveDraft)

| Field | Notes |
|---|---|
| id, organization, author | as MveDraft |
| name | default "New Maieutic session" |
| status | IN_PROGRESS, FINISHED (see section 9b) |
| current_stage | 1..6 |
| spec | JSON, the structure above |
| ade_snapshot | FK to the promoted ADE snapshot used |
| created_workbench | nullable FK, set when a workbench is created |
| outcome | null while IN_PROGRESS; WORKBENCH_WITH_RULE or WORKBENCH_WITHOUT_RULE once FINISHED |
| finished_at | set once, when the session is locked |
| allow_remote_pull | boolean, default false. Opt-in for Instance Sharing (section 9c) |
| tlp_classification | as MveDraft and `PlaybookGraph` (`TLP_CHOICES`) |
| created_at, updated_at | |

Autosave after each answered question. **Visibility: author only** (decided). Queries must
filter by `organization` and `author`; admins do not see other users' drafts.

## 9b. Lifecycle and locking

```
IN_PROGRESS  --(Create Workbench ...)-->  FINISHED  (locked, read-only, permanent)
```

- A finished session **stays in the Maieutics tab**. It is not deleted and does not move
  anywhere else. The Workbench is the editable object; the finished session is the record of
  how it was designed.
- **FINISHED is reached when the Workbench is created**, through either "Create Workbench and
  generate rule" or "Create Workbench without rule". The session locks at that moment, before
  any async rule generation completes. Otherwise the user could keep editing answers while the
  generator reads them. `outcome` records which exit was used. Rule generation progress and
  failures live on the Workbench, not on the session.
- `SAVE_DRAFT` does not finish the session; it stays IN_PROGRESS and editable.
- **Enforced on the server, not only in the UI.** Every mutation that changes a session (answer,
  stage change, spec edit, format selection, create) must reject a FINISHED session. The only
  mutations allowed on a FINISHED session are: toggle sharing (9c) and delete.
- **What a finished session shows:** the full spec, the ADE ledger with the snapshot each answer
  was given against, the STP block (claimed, evidence-supported, final, override reason), the
  completeness counts, the outcome, and a link to the created Workbench. The collapsible
  transcript is included. No input fields.
- **TLP is locked** with the rest of the session once it is FINISHED (decided). Choose the TLP
  before creating the Workbench. It decides sharing eligibility, so to share under a different TLP
  the session must be recreated. The Workbench's own TLP is a separate field and stays editable.
- **Delete** removes only the session record, never the Workbench. Allowed for the **author, an
  organization admin and a superuser** (decided), with a confirmation. Admins and superusers can
  delete but still cannot open or read another user's session (author-only visibility, section 9).
  So the Maieutics list for them shows only their own sessions; deleting someone else's session
  needs an explicit management path (for example by id from an admin view that shows metadata
  only: title, author, status, dates, no spec content). **[VERIFY with owner: confirm this
  metadata-only admin view is acceptable]** Deleting a session also removes it from future shares;
  copies already pulled by peers are not recalled.
- Drafts remain author-only (section 9). Finishing does not change visibility; sharing does not
  either (9c shares a copy through Instance Sharing, it does not make local sessions visible to
  other local users).

## 9c. Instance Sharing

Finished sessions can be shared with trusted peers through the existing Instance Sharing
feature as a new scope.

Verified in `backend/organizations/sharing.py` and `Docs/instance-sharing-tlp.md`. Each scope
today has: an entry in `ATOMIC_SCOPES` and `SCOPE_COLLECTIONS`, a payload builder, an entry in
the export `candidates` table (status filter plus opt-in filter), TLP filtering, an import
section, and a UI option in `InstanceSharing.tsx`. ACH is the closest precedent: status in
(FINISHED, APPROVED) plus `allow_remote_pull`.

| Item | Decision |
|---|---|
| Scope name / collection | `MAIEUTIC` / `maieutic_sessions` |
| Export eligibility | `status = FINISHED` **and** `allow_remote_pull = true` **and** passes the key's TLP maximum |
| Opt-in | Per session toggle, default **off**, owner-controlled. Same pattern as `allow_remote_pull` on ACH and Workbench (ACH has a dedicated mutation to toggle it) |
| Tags | Not applicable (sessions have no tags), like ACH, AdvOps and Capability |
| TLP | Applies, using the session's own `tlp_classification` |
| De-duplication | By normalized title, as other scopes |
| Payload | `spec`, ADE ledger, outcome, TLP, ADE snapshot identity (repo, ref, commit SHA) The conversation transcript is **excluded** (decided). |
| Not in payload | The local Workbench FK, author identity beyond what other scopes export **[VERIFY]**, any rule text (rules travel with the Workbench scope) |
| On import | Created as FINISHED and read-only in the receiving org, `allow_remote_pull` false (re-sharing requires a local opt-in, as for imported Workbenches), `created_workbench` null, TLP preserved, mapped through `HefaistosSharedObject` like other kinds so re-pulls update instead of duplicating. Shown in the Maieutics tab with an "imported" marker and its source |
| ADE history on import | The ledger keeps the ADE snapshot identity it was answered against, even if the receiving instance has never imported that snapshot. It is shown as history, not re-evaluated |

Sharing a session and sharing its Workbench are independent. A peer can receive the design
record without the Workbench, or the reverse.

### Compatibility safeguard (required)

`key_allows_scope(allowed_scopes, 'ALL')` currently returns true only if the key lists **every**
scope in `ATOMIC_SCOPES`. Adding `MAIEUTIC` would make existing keys that list the five original
scopes explicitly (without the `ALL` marker) fail with `PermissionDenied` when pulling `ALL`.

Required handling: an `ALL` pull must keep working for such keys and export only the scopes the
key permits. Existing keys must **not** be silently granted `MAIEUTIC`. Needs tests for: an
explicit-five key pulling `ALL`, an `ALL`-marker key pulling `ALL` (now includes sessions), a key
with only `MAIEUTIC`, and a peer on the older version receiving a payload with the new
collection.

### Where the code must change (Phase 6)

- `organizations/sharing.py`: `ATOMIC_SCOPES`, `SCOPE_COLLECTIONS`, a `_maieutic_payload_for_org`
  builder, the `candidates` table, the diagnostics summary, the import section and its summary
  counters, and `key_allows_scope` as above.
- `organizations/models.py`: scope validation for `allowed_scopes` (it rejects unsupported
  scopes).
- A mutation to toggle `allow_remote_pull` on a finished session (modelled on the ACH one).
- `frontend/src/pages/settings/InstanceSharing.tsx`: scope option and the collection key list.
- `Docs/instance-sharing-tlp.md`: add Maieutic to the TLP scope list and to "tags do not apply".

## 9a. Where generated rules are stored (verified)

A workbench has one primary `detection_rule` text plus `detection_rule_format`. Rules for
other formats are stored inside the `opentide_yaml` JSON, with the list of formats in
`configured_platforms`, saved through the existing `updatePlaybookOpentideYaml` mutation.

Today the rule editor applies async generation results **in the browser**
(`DetectionRuleEditorModal.tsx`). Maieutic closes after creating the workbench, so
generation results cannot rely on a modal staying open. Decision for Phase 6: the backend
writes each finished result into the workbench (primary into `detection_rule`, others into
`opentide_yaml`), so results survive the user navigating away. The workbench shows a banner
while tasks are pending.

## 10. Generation contract change

The current generator output contract is `rule-bundle-v1` with no constraints slot. Needs
`rule-bundle-v2`:

- the three constraint groups are passed in the user prompt
- output adds a `TRACEABILITY` section: `{ decision_ref, implemented: yes/no/partial, where, note }`
- the Prompt Registry gets separate keys: `maieutic.question`, `maieutic.evaluate`, and a
  new generation key or version for spec-driven generation

The traceability result is AI-assisted and must be labelled as a check, not a guarantee.

## 11. Open items

1. Which catalog fields exactly populate the dropdowns (Log Source first, Data Source second).
2. (Resolved: drafts are author-only. Finished sessions stay in the tab, locked, shareable: sections 9b and 9c.)
3. (Resolved, see 9a.)
4. Whether the KQL to AQL pass-through converter (`rules/conversion_service.py`) is fixed or
   removed. Maieutic will not use it either way.
5. (Resolved: TLP locked after finish, delete by author/admin/superuser, transcript not shared.) Remaining: confirm the metadata-only admin view for deleting other users' sessions (9b).
6. STP rules in section 5 reviewed by a detection engineer familiar with Summiting the Pyramid.
