# Rule Connector Testing Guide

## Scope

This file documents **current** rule-connector tests for RAG template ingestion into Qdrant.

The focus is language-aware ingestion for:

- `KQL`
- `EQL`
- `SPL`

## Primary RAG Regression Test

### `test_rag_sync.py`

Regression checks for template collection and normalization, including:

- Standard line-delimited JSONL ingestion
- JSON document fallback parsing (single object / list-style JSON)
- UTF-8 BOM-prefixed JSON handling
- Chat-style JSONL (`messages` with assistant query content)
- Language detection from language-scoped dataset paths (`data-kql`, `data-eql`, `data-spl`)
- Native file extension handling (`.eql`, `.spl`)
- **Strict JSONL language contract**:
  - fail ambiguous language rows
  - allow explicit per-row language without language-scoped path
  - fail row/dataset language mismatches

Run in container:

```bash
docker compose exec rule_connector python test_rag_sync.py
```

Run locally (if Python + deps are available):

```bash
python3 test_rag_sync.py
```

## Strict JSONL Language Contract (Current Behavior)

JSONL rows are ingested only when language is unambiguous:

1. Language is provided by row metadata (for example `language`, `format`, `rule_format`), **or**
2. Language is implied by dataset path/extension (`data-kql`, `data-eql`, `data-spl`, etc.)

Failure conditions:

- No resolvable language (ambiguous row/path)
- Explicit row language mismatches dataset language

In strict mode, these failures cause file-level ingestion failure with actionable error details.

## Useful Debug Commands

Tail connector logs:

```bash
docker compose logs -f rule_connector
```

Run only RAG test with unbuffered output:

```bash
docker compose exec rule_connector python -u test_rag_sync.py
```

## Notes

- Keep dataset corpora language-separated where possible (`data-kql`, `data-eql`, `data-spl`) to minimize ingestion ambiguity.
- Prefer explicit `language` metadata in JSONL when files are not stored in language-scoped folders.
