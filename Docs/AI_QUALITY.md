# AI Quality: coding phases and rule-generation pilot

## Phases

1. **Prompt governance foundation — implemented.** Code-owned product defaults,
   immutable deployment-local instruction versions, organization/installation
   scope, language overrides, explicit review, audited activation and rollback,
   and the Configuration → AI Quality interface.
2. **Generation provenance — started.** Async rule generation records its scope,
   effective instruction version, exact system/user prompts, prompt hashes,
   provider/model, assembled context, and retrieved excerpts. Next: persist
   provenance for synchronous generation and link generated output to saved
   artifact revisions, including multi-format rules and repeated generations.
3. **Structured correction feedback — next.** Preserve generated and corrected
   revisions, prepare diffs on save, collect user-confirmed issue categories and
   verification evidence, and provide an organization-scoped admin review queue.
   An edit alone must not be treated as a verified AI error.
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
generation path uses scoped approved instructions but does not yet persist a
generation snapshot.

## Validation

Backend coverage includes default resolution, approval gating, organization and
language isolation, precedence, immutable versions, stale-draft rejection,
upstream-default updates, rollback/reset, authorization, GraphQL review, exact
generation input capture, and worker provenance. Frontend coverage exercises
draft creation, explicit approval with a reason, and inherited-prompt preview.

The local full migration chain currently fails on SQLite because
`rules.0018_autocompleteevent_and_more` contains PostgreSQL-specific SQL.
The pilot tests were run using an isolated SQLite schema generated from models;
the new migration was also applied and reversed separately against its historical
schema, including organization backfill and preservation of existing task data.
PostgreSQL migration-chain and concurrent transaction validation remain rollout
checks for the deployment environment. No live-provider quality evaluation has
been performed; approved instructions are not automatically proven better.

The first increment passed 21 backend tests (including the existing generation
format tests), three AI Quality UI tests, a focused TypeScript check for the new
component/tests, the frontend production build, and composite GraphQL schema
validation. Three neighboring Configuration test failures were reproduced against
the original Configuration page. The repository-wide TypeScript check also has
existing errors outside the new component; these are not resolved by this change.
