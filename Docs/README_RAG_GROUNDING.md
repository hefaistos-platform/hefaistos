# RAG Rule Grounding (Qdrant Templates)

This document explains how HEFAISTOS uses Retrieval-Augmented Generation (RAG) for detection-rule quality, what is implemented today, and how to operate it effectively.

## Current Status (September 13, 2026)

Implemented and supported in production flow:

- Template sync into Qdrant for `KQL`, `EQL`, `SPL`, and `WAZUH`
- Dataset ingestion from `JSONL`, `.kql`/`.kusto`, `.eql`/`.esql`, and `.spl`
- Language-aware retrieval by output format (`KQL`/`EQL`/`SPL`/`WAZUH`)
- Grounded prompt injection for AI rule tasks
- Reuse assessment in Workbench for `KQL`, `EQL`, `SPL`, and `WAZUH`

Not yet implemented for template grounding:

- `AQL`, `OTHER`

## Why This Exists

The primary goal is to help generate near-production-quality rules with fewer AI hallucinations and fewer syntax/schema mistakes.

Without grounding, generic LLM output can:

- Invent table names or fields that do not exist
- Mix query dialects (for example SPL idioms inside KQL)
- Produce logically weak detection structure

With RAG grounding, generation is biased toward previously ingested, real query patterns from your repositories.

## What It Does

RAG grounding contributes three quality layers:

1. **Syntax quality**
   - Reinforces valid dialect-specific structure (KQL/EQL/SPL query shape, operators, command flow)

2. **Schema quality**
   - Surfaces likely table/index/field hints from retrieved examples
   - Reduces mismatched telemetry assumptions

3. **Logic quality**
   - Reuses realistic detection idioms (aggregation, thresholds, sequence patterns, filtering style)

This is strong guidance, not a hard parser-level guarantee.

## End-to-End Flow

1. **Repository configured for RAG sync**
   - In Repos configuration, set:
     - `ragSyncEnabled`
     - `ragDatasetPath` (path/glob)
     - `ragBranch`

2. **Sync event published**
   - `rule.repo.rag.sync.requested`

3. **Rule Connector ingests templates**
   - Clones repo branch
   - Scans dataset files
   - Normalizes each template with language metadata
   - Builds deterministic hash embedding

4. **Qdrant upsert/delete**
   - Upserts changed templates
   - Deletes stale templates for the same repository

5. **AI task retrieval**
   - During AI generation/improvement/similar/reuse flows, backend queries Qdrant by language + org scope
   - Injects strict grounding context into prompt

6. **Usage tracking**
   - Referenced RAG files are marked as used (`usage_count`, `last_used_at`)

## Supported Inputs and Language Separation

### File Types

- `JSONL`
  - Chat-style rows (`messages` with assistant content)
  - Object/list JSON fallback when line-delimited parsing is not possible
- Native rule files:
  - `.kql`, `.kusto` → `KQL`
  - `.eql`, `.esql` → `EQL`
  - `.spl` → `SPL`

### Language Attribution

Language is resolved in **strict mode**:

- Explicit row metadata (`language`, `format`, `rule_format`, etc.), or
- Language-scoped dataset path / extension (for example `data-kql`, `data-eql`, `data-spl`, `data-wazuh`, `.kql`, `.eql`, `.spl`)

Strict behavior:

- Ambiguous JSONL rows (no language metadata and no language-scoped path) fail ingestion
- JSONL rows with explicit language that mismatches dataset language fail ingestion
- No heuristic language inference from query content is used in strict mode

RAG file statuses are stored with explicit language, so mixed datasets are visible and auditable.

## Workbench and Backend Surfaces Using RAG

RAG template grounding is used in:

- `startGenerateRuleTask`
- `startSuggestImprovementsTask`
- `startGenerateSimilarRulesTask`
- `recommendReusableRuleFromRag`
- `generateResponsePlaybook` (language inferred from detection rule when available)

Frontend behavior:

- Workbench **RAG Reuse Check** is enabled for `KQL`, `EQL`, `SPL`, and `WAZUH`

## Relationship to Maieutic Engine

Maieutic currently uses Workbench context + ATT&CK/chokepoint grounding.

It does **not** directly call the Qdrant template RAG retriever in the Socratic questioning endpoint today.

Practical pattern:

- Use Maieutic to refine the analytical problem and investigation logic
- Use AI rule generation/improvement/reuse flows to apply template-grounded query synthesis

## Operating Recipe for `HEF-DATA`

For datasets structured as:

- `data-kql/hefaistos_kql_dataset.jsonl`
- `data-eql/hefaistos_eql_dataset.jsonl`
- `data-spl/hefaistos_spl_dataset.jsonl`
- `data-wazuh/hefaistos_wazuh_dataset.jsonl`

Recommended repository RAG settings:

- `ragSyncEnabled = true`
- `ragBranch = main` (or your active branch)
- `ragDatasetPath = data-kql,data-eql,data-spl,data-wazuh`

Then:

1. Run **Sync Now**
2. Verify RAG Files show ingested rows per language
3. In Workbench, choose output format (`KQL`/`EQL`/`SPL`/`WAZUH`)
4. Run generation + (optionally) reuse check

## Sync Reliability / Anti-Stuck Safeguards

To avoid long-lived `RUNNING`/`QUEUED` states and queue starvation:

- Rule connector git operations (`clone/fetch/pull`) are hard-limited by timeout (`RULE_CONNECTOR_GIT_SYNC_TIMEOUT_SECONDS`, default `600`).
- Scheduler watchdog marks stale `RUNNING`/`QUEUED` repository RAG states as `FAILED` after `RAG_SYNC_STALE_THRESHOLD_MINUTES` (default `90`).
- Optional auto-requeue (`RAG_SYNC_WATCHDOG_REQUEUE_STALE=true`) immediately re-queues stale repositories after watchdog failover.

This combination prevents one stuck sync from blocking later scheduled runs.

## How to Reach “Almost Perfect” Rule Quality

RAG quality is dominated by corpus quality. Recommended discipline:

1. Keep template corpora high-signal
   - Prefer tested production rules
   - Remove duplicates and outdated patterns

2. Keep metadata rich
   - Title, description, tags, tactic/technique, datasource hints

3. Keep language-separated corpora clean
   - Avoid mixed dialect examples in one dataset folder

4. Validate output in editor/LSP after generation
   - RAG improves quality substantially, but lint/validation remains required

5. Monitor ingestion health continuously
   - Failed files, skipped lines, stale datasets, low usage patterns

## Important Limitations

- RAG is guidance, not formal verification
- Embeddings are lightweight lexical hash vectors (fast, deterministic), not deep semantic encoders
- Final correctness still depends on target platform schema, telemetry quality, and analyst review

In short: RAG is a force multiplier for syntax/logical quality, but “perfect” still requires validation, testing, and human detection engineering judgment.
