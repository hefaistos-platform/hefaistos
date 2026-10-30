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
4. **Prompt improvement proposals — implemented for rule generation.** Draft
   instructions from accepted feedback, freeze correction/regression cases, replay
   baseline and candidate prompts, collect per-case admin assessments, and require
   approval of the exact evaluated version before activation.
5. **Component adapters and richer evaluation — later.** Add Maieutic turn/step
   feedback, OpenTIDE field/evidence feedback, and strAIn source/extraction feedback.
   Extend evaluation with curated holdout cases, format validators, and telemetry
   execution in supported test environments.

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
prompts, retrieval data, or mappings. Improvement proposals and evaluation have
their own workflow and require separate approval before activation.

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

## Improvement proposals and evaluation

The Improvement proposals card is available in Configuration → AI Quality for
organization admins and platform superusers, using the selected scope/language.
Choose one to five accepted feedback records. At least one must be reviewed with
root cause `PROMPT` and marked as a correction case. Accepted feedback with other
root causes may be added as regression cases, but cannot drive automatic prompt
suggestions. Non-prompt causes still need their own context/retrieval/code fixes.

Write revised instructions manually, or request an asynchronous AI suggestion.
The suggestion receives the current baseline and selected reviewed explanations
as untrusted JSON evidence. Its output must contain only instructions and a
rationale. It populates the editor for review; it creates no prompt version and
activates nothing. Admins supply per-case review criteria and optional required
and forbidden literal phrases before saving an immutable proposal. Revising it
creates a new proposal against the current effective baseline.

Each proposal freezes its feedback evidence, baseline, revised instructions,
criteria, assertions, and saved generation inputs. Evaluation uses the existing
AI generation worker and the requesting admin's effective provider settings.
It makes two calls per case, using the same provider/model and saved user prompt:
one with the baseline instructions and one with the proposed instructions. The
application output contract from the saved prompt remains intact. The selected
primary/quick-win/robust variant is evaluated. Corrected answers, review notes,
and assertions are never added to the replay prompt. No fresh Qdrant retrieval
occurs, so comparisons share the same captured context.

Checks require non-empty output, the selected variant's output delimiters, and
satisfaction of the configured case-sensitive literal phrases. These checks do
not prove syntax correctness or detection quality. Admins inspect both outputs,
assess logic and regression risk, and record a pass/fail decision with evidence
for **every** case. Assessment does not activate a prompt. Explicit approval
requires the latest evaluation to complete, its candidate checks and every
admin assessment to pass, and the effective baseline to remain unchanged.
The generic prompt-approval API enforces this gate for linked proposals too.
Existing manual prompt drafts retain their original approval workflow.

Failed checks cannot be waived by marking the manual assessment as passed.
A new run invalidates readiness from earlier runs, and changing instructions or
cases requires a new proposal and evaluation. A failed assessment is immutable;
rerun to reassess. Rejection is available without running an evaluation. The same
authorized admin can assess and approve; two-person review is not enforced.
Approved proposal versions use the existing scope precedence, audit history,
restore, and rollback mechanisms. They remain in the installation database and
are never exported with rules or written to tracked Git prompt files.

This is controlled replay of a small selected set, not statistical evidence of
improvement. Include regression cases and verify against representative telemetry.
Installation/all-language evaluations apply the proposed target instructions to
the selected saved cases; production organization/language overrides still follow
the documented precedence. Future component adapters and holdout/evaluation suites
will broaden this coverage. Live-provider quality experiments were not performed
while implementing the workflow.

Migration `ai_assistant.0019_ai_improvement_proposals` adds proposals, evaluations,
immutable completed results, and admin assessments, plus the new job types.
Deploy the updated backend, worker, and frontend together after migration. AI
suggestions and evaluation require configured AI credentials and RabbitMQ/worker
availability; queue failures are reported and can be retried. Prepared inputs and
partial outputs survive provider failures. Completed results remain available if
an originating task/user is deleted. If a task disappears before its completion
was assessed, rerun evaluation before approval. Records follow their proposal's deployment
scope, including organization cascade deletion for organization proposals.

## Validation

Backend coverage includes prompt scope/approval/rollback, immutable evidence,
per-format lineage, correction diffs, user submission/dismissal, verification
requirements, admin review, tenant isolation, rejected attribution rollback,
bulk partial results, MVE generation provenance, rule authoring, and FREE saves.
Proposal tests cover exact-input replay, immutable results and assessments,
activation gating, stale baselines, root-cause/scope restrictions, failed checks,
failed providers/queues, selected variants, duplicate jobs, and scoped GraphQL APIs.
Frontend coverage includes explicit prompt approval, correction submission,
intentional-edit dismissal, scoped feedback review, MVE attribution after edits,
background generation format isolation, selected-variant attribution, proposal creation,
AI suggestion/stale-result handling, per-case assessment, and explicit activation.

The local full migration chain fails on SQLite because
`rules.0018_autocompleteevent_and_more` contains PostgreSQL-specific SQL.
Behavioral tests use an isolated SQLite schema generated from models; migration
0018 and 0019 were applied and reversed separately against their referenced
historical schemas; 0019 also preserved existing task data. There is no model/migration drift in `ai_assistant`.
PostgreSQL full-chain and concurrent transaction validation remain deployment
checks. No live-provider quality evaluation has been performed.

The focused backend/UI suites, version-selection checks, composite GraphQL schema
validation, and frontend production build pass. Repository-wide TypeScript still
reports existing errors outside the new feedback implementation, including MVE
UI types and Configuration. These are not resolved by this change.
