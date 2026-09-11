import hashlib
import logging
import math
import os
import re
from collections import OrderedDict

import requests

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION_NAME = os.environ.get('QDRANT_TEMPLATE_COLLECTION', 'hefaistos_rule_templates')
DEFAULT_QDRANT_URL = os.environ.get('QDRANT_URL', 'http://qdrant:6333').rstrip('/')
DEFAULT_QDRANT_TIMEOUT = float(os.environ.get('QDRANT_TIMEOUT_SECONDS', '8'))
DEFAULT_VECTOR_SIZE = int(os.environ.get('QDRANT_TEMPLATE_VECTOR_SIZE', '256'))
SUPPORTED_RAG_LANGUAGES = {'KQL', 'EQL', 'SPL'}
RAG_LANGUAGE_ALIASES = {
    'KQL': 'KQL',
    'KUSTO': 'KQL',
    'EQL': 'EQL',
    'ELASTIC': 'EQL',
    'ESQL': 'EQL',
    'ES|QL': 'EQL',
    'SPL': 'SPL',
    'SPLUNK': 'SPL',
}


def normalize_rag_language(language: str | None, *, fallback: str = 'KQL') -> str | None:
    raw = str(language or '').strip().upper()
    normalized = RAG_LANGUAGE_ALIASES.get(raw, raw)
    if normalized in SUPPORTED_RAG_LANGUAGES:
        return normalized

    fallback_raw = str(fallback or '').strip().upper()
    fallback_normalized = RAG_LANGUAGE_ALIASES.get(fallback_raw, fallback_raw)
    if fallback_normalized in SUPPORTED_RAG_LANGUAGES:
        return fallback_normalized
    return None


def _tokenize(text: str):
    return re.findall(r'[a-zA-Z0-9_]{2,}', (text or '').lower())


def build_hash_embedding(text: str, size: int = DEFAULT_VECTOR_SIZE):
    vec = [0.0] * size
    tokens = _tokenize(text)
    if not tokens:
        return vec

    for token in tokens:
        digest = hashlib.sha256(token.encode('utf-8')).digest()
        idx = int.from_bytes(digest[:4], byteorder='big') % size
        vec[idx] += 1.0

    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _extract_kql_table_candidates(content: str) -> list[str]:
    text = content or ''
    candidates = []

    candidates.extend(re.findall(r'(?m)^\s*([A-Za-z_][A-Za-z0-9_]{2,})\s*\|', text))
    candidates.extend(re.findall(r'\b(?:from|join|lookup)\s+([A-Za-z_][A-Za-z0-9_]{2,})\b', text, flags=re.IGNORECASE))

    reserved = {
        'let', 'where', 'project', 'summarize', 'extend', 'order', 'serialize', 'distinct', 'take', 'limit',
        'count', 'search', 'datatable', 'mvexpand', 'evaluate', 'union', 'parse', 'parse_json', 'as', 'on',
        'inner', 'leftouter', 'rightouter', 'fullouter', 'kind', 'by', 'and', 'or', 'not',
    }

    deduped = OrderedDict()
    for table in candidates:
        normalized = str(table or '').strip()
        if not normalized:
            continue
        if normalized.lower() in reserved:
            continue
        deduped[normalized] = True

    return list(deduped.keys())


def _extract_eql_event_candidates(content: str) -> list[str]:
    text = content or ''
    candidates = []
    candidates.extend(re.findall(r'(?im)^\s*([A-Za-z_][A-Za-z0-9_.-]{2,})\s+where\b', text))
    candidates.extend(re.findall(r'\[\s*([A-Za-z_][A-Za-z0-9_.-]{2,})\s+where\b', text))

    reserved = {
        'sequence', 'any', 'where', 'by', 'with', 'maxspan', 'until', 'join', 'not', 'and', 'or',
    }

    deduped = OrderedDict()
    for candidate in candidates:
        normalized = str(candidate or '').strip()
        if not normalized:
            continue
        if normalized.lower() in reserved:
            continue
        deduped[normalized] = True
    return list(deduped.keys())


def _extract_spl_dataset_candidates(content: str) -> list[str]:
    text = content or ''
    candidates = []
    candidates.extend(re.findall(r'\bindex\s*=\s*([A-Za-z0-9_.*:-]+)', text, flags=re.IGNORECASE))
    candidates.extend(re.findall(r'\bsourcetype\s*=\s*([A-Za-z0-9_.*:-]+)', text, flags=re.IGNORECASE))
    candidates.extend(re.findall(r'\bsource\s*=\s*([A-Za-z0-9_.*:-]+)', text, flags=re.IGNORECASE))

    deduped = OrderedDict()
    for candidate in candidates:
        normalized = str(candidate or '').strip('"\'` ')
        if not normalized:
            continue
        deduped[normalized] = True
    return list(deduped.keys())


def _extract_query_hints(content: str, *, language: str = 'KQL') -> list[str]:
    normalized_language = normalize_rag_language(language, fallback='')
    if normalized_language == 'EQL':
        return _extract_eql_event_candidates(content)
    if normalized_language == 'SPL':
        return _extract_spl_dataset_candidates(content)
    return _extract_kql_table_candidates(content)


def _schema_value_to_text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, (list, tuple, set)):
        return ', '.join(str(item).strip() for item in value if str(item).strip())[:220]
    if isinstance(value, dict):
        parts = []
        for key, item in list(value.items())[:8]:
            key_text = str(key).strip()
            val_text = str(item).strip()
            if key_text and val_text:
                parts.append(f"{key_text}:{val_text}")
        return ', '.join(parts)[:220]
    return str(value).strip()[:220]


def summarize_reference_context(reference_context: list[dict]) -> dict:
    if not reference_context:
        return {
            'table_hints': [],
            'schema_hints': [],
            'source_refs': [],
            'repository_names': [],
            'languages': [],
        }

    table_hints = OrderedDict()
    schema_hints = OrderedDict()
    source_refs = OrderedDict()
    repository_names = OrderedDict()
    languages = OrderedDict()

    for ref in reference_context:
        if not isinstance(ref, dict):
            continue

        language = normalize_rag_language(str(ref.get('language') or '').strip(), fallback='')
        if language:
            languages[language] = True

        repository_name = str(ref.get('repository_name') or '').strip()
        if repository_name:
            repository_names[repository_name] = True

        source_ref = str(ref.get('source_ref') or ref.get('source_path') or '').strip()
        if source_ref:
            source_refs[source_ref] = True

        content = str(ref.get('content') or '')
        for table in _extract_query_hints(content, language=language or 'KQL'):
            table_hints[table] = True

        schema_context = ref.get('schema_context')
        if isinstance(schema_context, dict):
            for key, raw_value in schema_context.items():
                key_text = str(key or '').strip()
                value_text = _schema_value_to_text(raw_value)
                if key_text and value_text:
                    schema_hints[f"{key_text}={value_text}"] = True

    return {
        'table_hints': list(table_hints.keys()),
        'schema_hints': list(schema_hints.keys()),
        'source_refs': list(source_refs.keys()),
        'repository_names': list(repository_names.keys()),
        'languages': list(languages.keys()),
    }


def build_rag_query_text(
    playbook_context: dict | None = None,
    *,
    rule_content: str | None = None,
    additional_text: str | None = None,
) -> str:
    context = playbook_context if isinstance(playbook_context, dict) else {}

    parts = [
        str(context.get('title') or ''),
        str(context.get('strategy_name') or ''),
        str(context.get('goal') or ''),
        str(context.get('technique_id') or ''),
        str(context.get('technique_name') or ''),
        str(context.get('technical_context') or ''),
        str(context.get('existing_logic') or ''),
        str(context.get('data_sources') or ''),
        str(context.get('detection_focus_layer') or ''),
        str(context.get('false_positives') or ''),
        str(context.get('blind_spots') or ''),
        str(context.get('test_scenario') or ''),
        str(rule_content or ''),
        str(additional_text or ''),
    ]

    return "\n".join(part.strip() for part in parts if str(part or '').strip())


def retrieve_reference_context(
    *,
    playbook_context: dict | None = None,
    rule_content: str | None = None,
    additional_text: str | None = None,
    language: str = 'KQL',
    organization_id: str | None = None,
    limit: int = 6,
) -> list[dict]:
    normalized_language = normalize_rag_language(language, fallback='')
    if normalized_language not in SUPPORTED_RAG_LANGUAGES:
        return []

    query_text = build_rag_query_text(
        playbook_context,
        rule_content=rule_content,
        additional_text=additional_text,
    )
    if not query_text:
        return []

    try:
        retriever = QdrantTemplateRetriever()
        return retriever.search_templates(
            query_text,
            language=normalized_language,
            organization_id=str(organization_id) if organization_id else None,
            limit=limit,
        )
    except Exception as exc:
        logger.warning("RAG helper retrieval failed: %s", exc)
        return []


def mark_reference_files_used(reference_context: list[dict]):
    if not reference_context:
        return

    from django.db.models import F
    from django.utils import timezone
    from rules.models import RuleRepositoryRAGFileStatus

    now = timezone.now()
    unique_files = set()

    for ref in reference_context:
        if not isinstance(ref, dict):
            continue

        repository_id = str(ref.get('repository_id') or '').strip()
        source_path = str(ref.get('source_path') or '').strip()
        source_branch = str(ref.get('source_branch') or 'main').strip() or 'main'
        language = normalize_rag_language(ref.get('language'), fallback='KQL') or 'KQL'

        if not repository_id or not source_path:
            continue

        unique_files.add((repository_id, source_path, source_branch, language))

    for repository_id, source_path, source_branch, language in unique_files:
        try:
            updated = RuleRepositoryRAGFileStatus.objects.filter(
                repository_id=repository_id,
                source_path=source_path,
                source_branch=source_branch,
                language=language,
            ).update(
                used_in_generation=True,
                usage_count=F('usage_count') + 1,
                last_used_at=now,
            )

            if updated == 0:
                RuleRepositoryRAGFileStatus.objects.create(
                    repository_id=repository_id,
                    source_path=source_path,
                    source_branch=source_branch,
                    language=language,
                    ingestion_status=RuleRepositoryRAGFileStatus.IngestionStatus.INGESTED,
                    templates_count=0,
                    last_synced_at=now,
                    used_in_generation=True,
                    usage_count=1,
                    last_used_at=now,
                )
        except Exception as exc:
            logger.warning(
                "Failed to mark RAG file usage (repo=%s path=%s): %s",
                repository_id,
                source_path,
                exc,
            )


def build_reference_context_prompt(reference_context: list[dict]) -> str:
    if not reference_context:
        return ''

    summary = summarize_reference_context(reference_context)
    summary_languages = summary.get('languages') or []
    if len(summary_languages) == 1:
        language_label = summary_languages[0]
    elif len(summary_languages) > 1:
        language_label = '/'.join(summary_languages)
    else:
        language_label = 'QUERY'

    table_hints = ', '.join(summary['table_hints'][:24]) or 'No table hints detected.'
    schema_hints = '; '.join(summary['schema_hints'][:16]) or 'No schema hints detected.'
    source_refs = ', '.join(summary['source_refs'][:12]) or 'No source refs.'

    blocks = []
    for idx, ref in enumerate(reference_context, start=1):
        block = [
            f"EXAMPLE #{idx}",
            f"TITLE: {ref.get('title') or 'Untitled'}",
            f"SOURCE: {ref.get('source_ref') or ref.get('source_path') or 'unknown'}",
            f"REPOSITORY: {ref.get('repository_name') or 'unknown'}",
            f"LANGUAGE: {ref.get('language') or 'KQL'}",
        ]
        description = (ref.get('description') or '').strip()
        if description:
            block.append(f"DESCRIPTION: {description}")

        schema_context = ref.get('schema_context') if isinstance(ref.get('schema_context'), dict) else {}
        if schema_context:
            schema_pairs = []
            for key, raw_value in schema_context.items():
                key_text = str(key or '').strip()
                value_text = _schema_value_to_text(raw_value)
                if key_text and value_text:
                    schema_pairs.append(f"{key_text}={value_text}")
            if schema_pairs:
                block.append("SCHEMA_CONTEXT: " + '; '.join(schema_pairs[:8]))

        example_tables = _extract_query_hints(
            ref.get('content') or '',
            language=str(ref.get('language') or 'KQL'),
        )
        if example_tables:
            block.append("TABLE_HINTS: " + ', '.join(example_tables[:12]))

        block.append("QUERY:")
        block.append(ref.get('content') or '')
        blocks.append('\n'.join(block))

    return (
        f"STRICT RETRIEVED {language_label} GROUNDING CONTEXT\n"
        "Use this context to validate likely table names, field patterns, and query logic idioms.\n"
        "Prefer these grounded structures over invented ones when compatible with the workbench goal.\n"
        f"TABLE NAME HINTS: {table_hints}\n"
        f"SCHEMA / FIELD HINTS: {schema_hints}\n"
        f"SOURCE REFERENCES: {source_refs}\n\n"
        + "\n\n".join(blocks)
    )


class QdrantTemplateRetriever:
    def __init__(
        self,
        base_url: str = DEFAULT_QDRANT_URL,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        vector_size: int = DEFAULT_VECTOR_SIZE,
        timeout_seconds: float = DEFAULT_QDRANT_TIMEOUT,
        api_key: str | None = None,
    ):
        self.base_url = (base_url or DEFAULT_QDRANT_URL).rstrip('/')
        self.collection_name = collection_name or DEFAULT_COLLECTION_NAME
        self.vector_size = int(vector_size or DEFAULT_VECTOR_SIZE)
        self.timeout_seconds = float(timeout_seconds or DEFAULT_QDRANT_TIMEOUT)
        self.api_key = api_key or os.environ.get('QDRANT_API_KEY')

    def _headers(self):
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['api-key'] = self.api_key
        return headers

    def _request(self, method: str, path: str, payload=None):
        url = f"{self.base_url}{path}"
        response = requests.request(
            method,
            url,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        if not response.text:
            return {}
        return response.json()

    def _get_collection_vector_size(self):
        response = self._request('GET', f"/collections/{self.collection_name}")
        vectors_config = (((response.get('result') or {}).get('config') or {}).get('params') or {}).get('vectors')

        if isinstance(vectors_config, dict):
            direct_size = vectors_config.get('size')
            if direct_size is not None:
                try:
                    return int(direct_size)
                except (TypeError, ValueError):
                    return None

            for value in vectors_config.values():
                if not isinstance(value, dict):
                    continue
                named_size = value.get('size')
                if named_size is None:
                    continue
                try:
                    return int(named_size)
                except (TypeError, ValueError):
                    continue

        return None

    def ensure_collection(self):
        payload = {
            'vectors': {
                'size': self.vector_size,
                'distance': 'Cosine',
            }
        }
        try:
            self._request('PUT', f"/collections/{self.collection_name}", payload)
            return
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code != 409:
                raise

        try:
            existing_size = self._get_collection_vector_size()
        except Exception as exc:
            logger.warning(
                "Qdrant collection '%s' already exists; continuing after create conflict (config lookup failed: %s)",
                self.collection_name,
                exc,
            )
            return

        if existing_size and existing_size != self.vector_size:
            logger.warning(
                "Qdrant collection '%s' already exists with vector size %s (configured %s). Using existing size.",
                self.collection_name,
                existing_size,
                self.vector_size,
            )
            self.vector_size = existing_size

    def search_templates(
        self,
        query_text: str,
        *,
        language: str = 'KQL',
        organization_id: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        if not (query_text or '').strip():
            return []

        try:
            self.ensure_collection()
        except Exception as exc:
            logger.warning("Qdrant collection check failed: %s", exc)
            return []

        normalized_language = normalize_rag_language(language, fallback='KQL') or 'KQL'
        must_filters = [{'key': 'language', 'match': {'value': normalized_language}}]
        if organization_id:
            must_filters.append({'key': 'organization_id', 'match': {'value': str(organization_id)}})

        payload = {
            'vector': build_hash_embedding(query_text, self.vector_size),
            'limit': max(1, min(int(limit or 5), 20)),
            'with_payload': True,
            'with_vector': False,
            'filter': {
                'must': must_filters,
            },
        }

        try:
            response = self._request('POST', f"/collections/{self.collection_name}/points/search", payload)
        except Exception as exc:
            logger.warning("Qdrant search failed: %s", exc)
            return []

        results = []
        for hit in (response.get('result') or []):
            payload_data = hit.get('payload') or {}
            content = (payload_data.get('content') or '').strip()
            if not content:
                continue
            results.append({
                'id': str(hit.get('id')),
                'score': float(hit.get('score') or 0.0),
                'repository_id': payload_data.get('repository_id') or '',
                'title': payload_data.get('title') or 'Untitled',
                'description': payload_data.get('description') or '',
                'content': content,
                'language': normalize_rag_language(payload_data.get('language'), fallback=normalized_language) or normalized_language,
                'repository_name': payload_data.get('repository_name') or '',
                'source_path': payload_data.get('source_path') or '',
                'source_ref': payload_data.get('source_ref') or '',
                'source_branch': payload_data.get('source_branch') or '',
                'schema_context': payload_data.get('schema_context') or {},
            })

        return results
