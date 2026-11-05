# Adversarial Detection Engineering (ADE) in HEFAISTOS

This document explains how the ADE framework is imported into HEFAISTOS, how to operate it
safely, and what it is (and is not) used for.

Upstream source:
- `https://github.com/Adversarial-Detection-Engineering/Adversarial-Detection-Engineering-Framework`

Site: `https://adeframework.org/`

> **Status.** The import, staging, diff, promote and rollback pipeline described here is
> implemented. The consumers of ADE content (Maieutic Engine 3.0 questions and hints) are
> planned in `Docs/MAIEUTIC_3_PLAN.md` and are not built yet. Until then, promoting a snapshot
> changes only what is stored and shown on the Framework Updates page.

## What ADE is

ADE classifies how **detection logic** can miss in-scope activity (false negatives). It has
four categories and sixteen subcategories:

| Category | Idea |
|---|---|
| ADE1 Reformatting in Actions | The attacker rewrites the action so a string match fails |
| ADE2 Omit Alternatives | The rule covers one method, version, location or file type, and others are omitted |
| ADE3 Context Development | The attacker shapes the context the rule relies on (cloning, aggregation, timing, lineage, limits) |
| ADE4 Logic Manipulation | The rule's boolean or field logic is wrong or invertible |

It also ships a 14-item **Bug Likelihood Test**, 16 rule-specific bypass examples (DLE) and 7
in-the-wild records (ITW).

**What ADE is not.** It does not measure false positives, telemetry health or overall rule
quality, and it cannot certify a rule as complete. It is also not the same thing as
Summiting the Pyramid robustness: STP is about how hard the observable is to evade, ADE is
about whether the logic covers the behaviour. HEFAISTOS keeps the two separate.

## Core design principles

1. **No auto-apply from upstream.** Imports create a STAGED snapshot. Nothing changes until a
   superuser promotes it.
2. **Stable IDs.** Entries are keyed by upstream IDs (`ADE3-01`, `DLE-2026-00001`). Titles can be
   renamed upstream without breaking references.
3. **Layout changes are visible, not silent.** Upstream has no machine-readable taxonomy
   (subcategories are Markdown headings), so the parser reports warnings and fails the snapshot
   if no subcategory was found.
4. **Rollback is one click.** The previous ACTIVE snapshot is ARCHIVED on promotion and can be
   re-activated.
5. **Independent of Chokepoints.** ADE has its own models and operations. The Chokepoints code
   path is unchanged.

## Data model

All in `backend/platform_data/models.py`.

| Model | Purpose |
|---|---|
| `AdeSnapshot` | One imported version. Status STAGED, ACTIVE, FAILED or ARCHIVED. Stores repo, ref, commit SHA, summary counters and warnings |
| `AdeEntry` | One record in a snapshot. `kind` is CATEGORY, SUBCATEGORY, LIKELIHOOD_CHECK, DLE or ITW. Has `ade_id`, `title`, `definition`, `related_ade`, `mitre_attack`, `logsource`, a `source_hash` for diffing and the full parsed `content` |
| `AdeImportJob` | One import run triggered from the UI, with status, log and error |
| `PlatformDataVersion` | Gets a row with framework `ade-framework` when a snapshot is promoted, so it appears in "Currently Loaded Frameworks" |

Entry keys: `SUBCATEGORY:ADE3-01`, `CATEGORY:ADE3`, `DLE:DLE-2026-00001`, `ITW:ITW-2026-00001`,
and `LIKELIHOOD_CHECK:01` (checks have no upstream ID, so they are keyed by position).

## End-to-end flow

1. A superuser runs **Run ADE Import** (Framework Updates page).
2. A background thread runs `import_ade_framework`, which reads the upstream files, normalizes
   them and writes a STAGED snapshot with its entries.
3. The page shows a **diff** against the active snapshot: added, changed, renamed, removed,
   unchanged, plus a per-entry list.
4. The superuser promotes the snapshot. The previous active one becomes ARCHIVED and the
   `ade-framework` version row is updated.
5. To undo, pick an ARCHIVED snapshot as the rollback target.

## How parsing works

Code: `backend/platform_data/ade_sync.py`.

| Upstream file | Read as |
|---|---|
| `docs/taxonomy/ade*.md` | Category from `# ADEn - Title`. Subcategories from `### ADEn-nn: Title` headings **inside the `## Subcategories` section only**, with the text after `**Definition:**` as the definition. Headings without a colon (for example `### ADE4-01 Patterns`) and headings after that section are ignored |
| `docs/guides/bug-likelihood-test.md` | Each `- [ ]` item is one check. ADE IDs in the indented lines that follow become `related_ade` |
| `dle/<year>/DLE-*.yaml` | Rule-specific bypass example |
| `in-the-wild/ITW-*.yaml` | Threat-actor bypass record |

Upstream uses the non-breaking hyphen (U+2011) in some ADE IDs, so dashes are normalized
before matching.

Parsers never raise on odd content. They return what they found plus warnings.

### Warnings

A snapshot records a warning (shown in the snapshots table, still STAGED) when:

- a taxonomy file has no `## Subcategories` section or no `**Definition:**` for a subcategory;
- a DLE, ITW or likelihood check refers to an ADE ID that has no subcategory;
- a YAML record has an unknown `schema_version` (known: `1.0`);
- a YAML file is invalid, or has no usable `id`;
- an entry key appears twice.

### Snapshot failure behaviour

A snapshot is marked **FAILED** (and cannot be promoted or rolled back to) when no subcategory
was parsed. The taxonomy is the point of this framework, so zero subcategories almost certainly
means the upstream layout changed. Fix the parser, then re-run the import.

## Reading the diff

| Label | Meaning |
|---|---|
| ADDED | Key exists only in the staged snapshot (for example a new subcategory) |
| CHANGED | Same key, different content |
| RENAMED | Same key and definition, different title (upstream renamed ADE2-01 this way) |
| REMOVED | Key exists only in the active snapshot |

`RENAMED` is counted with changed in the totals.

## UI usage (superuser)

Framework Updates page, ADE section (bottom):

1. **Adversarial Detection Engineering (ADE)**: source, active snapshot, counts per kind,
   latest upstream revision, and a banner when a newer revision exists.
2. **Run ADE Update**: repository, ref and mode. `Local` reads from a path on the server
   and is intended for diagnostics (see the note below).
3. **ADE Snapshot Promotion**: choose a staged snapshot, review the diff, promote. Choose an
   archived snapshot to roll back.
4. **ADE Snapshots**: history with summary and warnings.
5. **Recent ADE Import Jobs**: status, duration and errors.

Only superusers can view or run any of this.

## API surface (GraphQL)

Queries (superuser): `activeAdeSnapshot`, `adeSnapshot(id)`, `adeSnapshots(status, limit)`,
`adeEntries(snapshotId, kind)` (defaults to the active snapshot), `adeImportJob(id)`,
`adeImportJobs(limit)`, `stagedAdeDiff(snapshotId)`.
`latestAvailableAdeRevision(sourceRepo, ref)` resolves the upstream commit SHA (cached 1 hour,
null on network errors).

Mutations (superuser): `runAdeImport(sourceRepo, ref, mode)`, `promoteAdeSnapshot(snapshotId)`,
`rollbackAdeSnapshot(snapshotId)`.

`runAdeImport` refuses to start while another ADE import is PENDING or RUNNING. Jobs stuck for
more than 15 minutes (for example after a backend restart, since imports run in a thread) are
marked FAILED automatically at the start of the next import, so the button recovers on its own.

## Manual import command

```bash
docker compose exec backend python manage.py import_ade_framework --mode remote
docker compose exec backend python manage.py import_ade_framework --mode local --dir /path/to/ade
```

The command only stages a snapshot. It never activates it.

> **Note on `LOCAL` mode from the UI.** The path is read on the backend server or container,
> not on your workstation.

## Migrations

`platform_data/migrations/0014_ade_framework.py` adds the three models and the new
`PlatformDataVersion` choice.

```bash
docker compose exec backend python manage.py migrate platform_data
```

## Tests

```bash
docker compose exec backend python manage.py test platform_data.tests_ade
```

Covers parsing (including the non-breaking hyphen and ignored headings), warnings, the import
command (local mode, re-import, layout-change failure), diff labels, promote and rollback,
superuser guards, and the stale-job watchdog.

## Upstream change strategy

| Upstream change | What happens |
|---|---|
| New subcategory | Appears as ADDED in the diff |
| Subcategory renamed | RENAMED, same ID |
| Definition edited | CHANGED |
| Subcategory removed | REMOVED |
| New DLE or ITW record | ADDED, picked up with no parser change |
| YAML `schema_version` changes | Warning on the snapshot |
| Markdown layout changes | Warnings, or FAILED if no subcategory is found |

HEFAISTOS-authored question text and hints per ADE ID live in the repository, not in this import.
A new upstream subcategory therefore has no question until someone adds a question file for it.
See `Docs/MAIEUTIC_ADE_QUESTIONS.md`.

## Current limits

- The Markdown taxonomy parser depends on upstream heading conventions.
- Only `github.com` repositories are accepted for remote imports.
- ADE content is stored and shown, but not yet used by Maieutic or rule review.

## File map

- `backend/platform_data/ade_sync.py`: GitHub access and parsers
- `backend/platform_data/management/commands/import_ade_framework.py`: import command
- `backend/platform_data/models.py`: `AdeSnapshot`, `AdeEntry`, `AdeImportJob`
- `backend/platform_data/schema.py`: GraphQL types, queries, mutations, diff, promotion
- `backend/platform_data/tasks.py`: background import thread and stale-job watchdog
- `backend/platform_data/tests_ade.py`: tests
- `frontend/src/components/framework/AdeFrameworkSection.tsx`: Framework Updates UI
