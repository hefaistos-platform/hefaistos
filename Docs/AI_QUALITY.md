# AI Quality: coding phases and rule-generation pilot

## Phases

1. **Prompt governance foundation — implemented.** Code-owned product defaults,
   immutable deployment-local instruction versions, organization/installation
   scope, language overrides, explicit review, audited activation and rollback,
   and the Configuration → AI Quality interface.
2. **Generation provenance — implemented for the rule-generation pilot.** Async
   rule generation and synchronous MVE rule generation retain prepared prompts,
   context, provider/model, and immutable output artifacts. Saved revisions keep
   per-format lineage across reopened editors and repeated generations.
3. **Structured correction feedback — implemented.** Saves prepare correction
   diffs, users explain or dismiss edits, and administrators review structured
   evidence in an organization-scoped queue. An edit alone is an unconfirmed
   candidate, not a verified AI error.
4. **Improvement proposals and component adapters — later.** Group reviewed
   feedback, distinguish prompt/context/retrieval/code causes, draft improvements,
   evaluate representative cases, and require approval of the exact proposal.
   Add Maieutic turn/step feedback, OpenTIDE field/evidence feedback, and strAIn
   source/extraction feedback through component-specific schemas.

## Current behavior

Open `/mgmt/config?tab=aiquality`. Organization `ADMIN` users manage their own
organization. Platform superusers can choose installation scope or an
organization. Configuration access, `is_staff`, and service-account usernames
do not grant prompt management permission. Bot auditors cannot manage prompts.

The pilot exposes the instructions for `rule_generation.generate`. It is not a
catalog of every AI operation yet. Prompt instructions are plain text; they are
not executed as templates or code. Required output delimiters, format
requirements, context assembly, and parsing remain controlled by the application.

For a requested language, resolution uses this precedence:

1. Organization override for that language.
2. Organization override for all languages.
3. Installation override for that language.
4. Installation override for all languages.
5. Product default from `ai_assistant/prompt_defaults.py`.

Defaults work without seeding database rows. A draft is an immutable proposal
containing its starting instructions, baseline fingerprint, new instructions,
content hash, author, and reason. Editing a proposal means creating a new draft.
Approval records the reviewer and reason and activates that exact version.
Rejected drafts cannot be activated. The same authorized admin may author and
approve a manual draft; two-person approval is not enforced in this pilot.

Approval fails if the effective baseline changed after drafting. Restore/reset
operations also check the reviewed effective fingerprint; reset additionally
checks the inherited instructions shown in the confirmation dialog. Mutations
serialize changes for the same prompt key across scopes and languages.

The UI displays the latest 50 versions and 100 audit events for a scope/language.
Older records remain stored. Django admin offers superusers read-only inspection;
all prompt changes use the application approval workflow.

## Persistence and upgrades

Local instructions, approvals, and audit history live in database tables. They
are never written into tracked prompt files, repository clones, or Git publishing
jobs. Existing rule publishing does not export these records.

Changing a product default affects scopes inheriting that default; it does not
overwrite approved local overrides. Future releases should increment the default
version when its instructions change. Upstream/local reconciliation is a future
extension, not an automatic merge.

MGMT Cave's existing prompt catalog and seed command remain separate from this
registry. Its existing overwrite behavior must be addressed when migrating that
component; the new rule-generation registry is not managed by that command.

Back up these tables with the installation database. Prompt/context snapshots
can contain sensitive operational content and should follow the deployment's
database access and retention policy. No export/import feature is introduced in
this phase.

## Rollout

Apply `python manage.py migrate` with the deployment's usual configuration, then
restart the backend and AI generation worker and deploy the frontend build.
The feature does not require any model call or an approved override to initialize.

Migration `ai_assistant.0017_ai_quality_prompt_versions` also adds an organization
snapshot to async tasks. Existing tasks are backfilled from their user's current
organization; historical membership cannot be reconstructed from old task rows.
New tasks snapshot organization when queued. Rule generation refuses execution
if the user's organization changes before the worker runs. Task polling is
restricted to the requesting user's current organization.

Async rule-generation snapshots are stored in `AIGenerationTask.prompt_provenance`
before invoking the provider, so provider failures do not erase the prepared
input. Provider credentials are not copied into this record. Retrieved excerpts
are retained with the prepared prompt; `rag_status` records whether references
were found, absent, unsupported, or retrieval raised an error. The synchronous MVE
rule-generation path also records a task, prepared input, and generation artifact
before handing the generated rule to the editor.

## Correction feedback

Rule-generation output is captured as immutable evidence, with separate primary,
quick-win, and robust variants. Each artifact retains the raw provider output,
cleaned editor content, format, originating context, author, and prompt/context
snapshot. Saving a rule records a per-format revision and its generation source.
The initial comparison uses content before server-generated metadata is injected.
Previously saved metadata already present in an editor remains part of its content.

The editor shows pending candidates after a save. Users choose issue categories
(table, field, logic, syntax, missing context, false positives, output structure,
formatting, changed requirements, or other), explain what was wrong and how they
resolved it, and provide their verification level and evidence. Evidence is
required for verification claims and is labeled **user-reported**. Intentional
edits can be dismissed with a reason. A newer save supersedes older unsubmitted
candidates; submitted feedback remains available for review.

Configuration → AI Quality includes a feedback queue filtered by organization,
format, and status. Organization admins review their organization; platform
superusers can review all organizations. Reviewers inspect the diff, explanation,
exact generation context/prompts, versioned JSON payload, and audit history, then
accept or reject with a reason and likely root cause. Acceptance does not update
prompts, retrieval data, or mappings. Improvement proposals and evaluation remain
phase 4, with separate approval before activation.

Attribution survives reopening a saved rule and is replaced by an explicit new
generation. Imports and currently untracked AI operations detach the previous
source to avoid blaming unrelated output on the original generation. FREE format
is excluded. Standalone Rule Hub drafts and Workbench single/bulk saves capture
per-format evidence; invalid bulk attribution fails that format while reporting
other saved formats. Rule deletion preserves feedback snapshots; organization
deletion removes its records.

The pilot covers rule generation, including rules generated from MVE context.
Maieutic conversations, OpenTIDE enrichment, strAIn, generate-all conversion,
RAG adaptation, and improvement suggestions do not yet have their own feedback
adapters. Existing content and generations from before this feature cannot be
retroactively attributed. Installation-local feedback is stored only in the
application database and is excluded from rule publishing and Git exports.

Migration `ai_assistant.0018_ai_rule_feedback` creates generation artifacts,
revisions, lineage, feedback, and feedback audit tables. Apply both 0017 and 0018
when upgrading from a deployment without the AI Quality foundation.

## Validation

Backend coverage includes prompt scope/approval/rollback, immutable evidence,
per-format lineage, correction diffs, user submission/dismissal, verification
requirements, admin review, tenant isolation, rejected attribution rollback,
bulk partial results, MVE generation provenance, rule authoring, and FREE saves.
Frontend coverage includes explicit prompt approval, correction submission,
intentional-edit dismissal, scoped feedback review, MVE attribution after edits,
background generation format isolation, and selected-variant attribution.

The local full migration chain fails on SQLite because
`rules.0018_autocompleteevent_and_more` contains PostgreSQL-specific SQL.
Behavioral tests use an isolated SQLite schema generated from models; migration
0018 was applied and reversed separately against its directly referenced
historical schema. There is no model/migration drift in `ai_assistant`.
PostgreSQL full-chain and concurrent transaction validation remain deployment
checks. No live-provider quality evaluation has been performed.

The focused backend/UI suites, version-selection checks, composite GraphQL schema
validation, and frontend production build pass. Repository-wide TypeScript still
reports existing errors outside the new feedback implementation, including MVE
UI types and Configuration. These are not resolved by this change.
