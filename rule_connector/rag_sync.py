import glob
import hashlib
import json
import logging
import math
import os
import re
import uuid
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION_NAME = os.environ.get('QDRANT_TEMPLATE_COLLECTION', 'hefaistos_rule_templates')
DEFAULT_QDRANT_URL = os.environ.get('QDRANT_URL', 'http://qdrant:6333').rstrip('/')
DEFAULT_QDRANT_TIMEOUT = float(os.environ.get('QDRANT_TIMEOUT_SECONDS', '10'))
DEFAULT_VECTOR_SIZE = int(os.environ.get('QDRANT_TEMPLATE_VECTOR_SIZE', '256'))
SUPPORTED_RAG_LANGUAGES = {'KQL', 'EQL', 'SPL'}
LANGUAGE_ALIASES = {
    'KQL': 'KQL',
    'KUSTO': 'KQL',
    'EQL': 'EQL',
    'ELASTIC': 'EQL',
    'ESQL': 'EQL',
    'ES|QL': 'EQL',
    'SPL': 'SPL',
    'SPLUNK': 'SPL',
}
EXTENSION_LANGUAGE_MAP = {
    '.kql': 'KQL',
    '.kusto': 'KQL',
    '.eql': 'EQL',
    '.esql': 'EQL',
    '.spl': 'SPL',
}

# STRICT mode: JSONL template language must be explicitly known from either
# language-scoped dataset path/extension or row-level language metadata.
STRICT_JSONL_LANGUAGE = True

JSONL_LANGUAGE_FIELDS = (
    'language',
    'format',
    'rule_format',
    'query_language',
    'dialect',
    'type',
    'section',
    'engine',
)


def _normalize_language(raw_language, *, fallback: str = 'KQL'):
    value = str(raw_language or '').strip().upper()
    normalized = LANGUAGE_ALIASES.get(value, value)
    if normalized in SUPPORTED_RAG_LANGUAGES:
        return normalized

    fallback_value = str(fallback or '').strip().upper()
    fallback_normalized = LANGUAGE_ALIASES.get(fallback_value, fallback_value)
    if fallback_normalized in SUPPORTED_RAG_LANGUAGES:
        return fallback_normalized
    return ''


def _language_from_source_path(source_path: str, *, ext: str = ''):
    extension = str(ext or '').strip().lower()
    if extension in EXTENSION_LANGUAGE_MAP:
        return EXTENSION_LANGUAGE_MAP[extension]

    normalized_source_path = str(source_path or '').replace('\\', '/').strip('/').lower()
    normalized_path = f"/{normalized_source_path}/"
    if '/data-eql/' in normalized_path or '/eql/' in normalized_path:
        return 'EQL'
    if '/data-spl/' in normalized_path or '/spl/' in normalized_path or '/splunk/' in normalized_path:
        return 'SPL'
    if '/data-kql/' in normalized_path or '/kql/' in normalized_path:
        return 'KQL'
    return ''


def _detect_language_from_text(*text_parts: str):
    text = "\n".join(str(part or '') for part in text_parts if str(part or '').strip())
    lowered = text.lower()
    if not lowered:
        return ''

    scores = {
        'KQL': 0,
        'EQL': 0,
        'SPL': 0,
    }

    if re.search(r'\b(index|sourcetype|source|host)\s*=\s*', lowered):
        scores['SPL'] += 4
    if re.search(r'\|\s*(stats|eval|rex|table|tstats|mstats|lookup|eventstats|streamstats)\b', lowered):
        scores['SPL'] += 3
    if 'splunk' in lowered or re.search(r'\bspl\b', lowered):
        scores['SPL'] += 2

    if re.search(r'(^|\n)\s*(sequence|any\s+where|process\s+where|file\s+where|network\s+where|registry\s+where)\b', lowered):
        scores['EQL'] += 4
    if 'elastic eql' in lowered or re.search(r'\beql\b', lowered) or 'es|ql' in lowered:
        scores['EQL'] += 2

    if re.search(r'\|\s*(project|summarize|extend|mv-expand|project-away|project-rename|distinct)\b', lowered):
        scores['KQL'] += 3
    if re.search(r'\b(deviceprocessevents|devicenetworkevents|devicefileevents|securityevent|signinlogs|auditlogs|commonsecuritylog)\b', lowered):
        scores['KQL'] += 3
    if 'kusto' in lowered or re.search(r'\bkql\b', lowered):
        scores['KQL'] += 2

    best_language = max(scores.items(), key=lambda item: item[1])
    if best_language[1] <= 0:
        return ''
    return best_language[0]


def _extract_explicit_template_language(entry: dict):
    if not isinstance(entry, dict):
        return ''

    for field in JSONL_LANGUAGE_FIELDS:
        normalized = _normalize_language(entry.get(field), fallback='')
        if normalized in SUPPORTED_RAG_LANGUAGES:
            return normalized
    return ''


def _infer_template_language(
    entry: dict,
    *,
    source_path: str,
    source_ext: str,
    content: str,
    extracted: dict | None = None,
    language_hint: str | None = None,
    allow_content_inference: bool = False,
):
    explicit_language = _extract_explicit_template_language(entry)
    if explicit_language:
        return explicit_language

    from_path = _language_from_source_path(source_path, ext=source_ext)
    if from_path:
        return from_path

    if allow_content_inference:
        schema_hint = (extracted or {}).get('schema_hint') if isinstance(extracted, dict) else ''
        inferred_from_text = _detect_language_from_text(schema_hint, content)
        if inferred_from_text:
            return inferred_from_text

    return _normalize_language(language_hint, fallback='')


def _compute_content_hash(*, language: str, title: str, description: str, content: str, tags: list[str], schema_context: dict):
    normalized_schema = schema_context if isinstance(schema_context, dict) else {}
    digest_payload = {
        'language': str(language or '').upper(),
        'title': str(title or '').strip(),
        'description': str(description or '').strip(),
        'content': str(content or '').strip(),
        'tags': [str(tag).strip() for tag in (tags or []) if str(tag).strip()],
        'schema_context': normalized_schema,
    }
    digest_text = json.dumps(digest_payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(digest_text.encode('utf-8')).hexdigest()


def _tokenize(text: str):
    return re.findall(r'[a-zA-Z0-9_]{2,}', (text or '').lower())


def _hash_embedding(text: str, size: int = DEFAULT_VECTOR_SIZE):
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


def _stable_point_id(repo_id: str, source_ref: str):
    # Qdrant string point IDs must be UUIDs.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{repo_id}:{source_ref}"))


def _coerce_tags(raw_tags):
    if raw_tags is None:
        return []
    if isinstance(raw_tags, list):
        return [str(tag).strip() for tag in raw_tags if str(tag).strip()]
    if isinstance(raw_tags, str):
        return [tag.strip() for tag in raw_tags.split(',') if tag.strip()]
    return [str(raw_tags).strip()] if str(raw_tags).strip() else []


def _extract_from_chat_messages(entry: dict):
    """Extract query template content from ChatML/fine-tune JSONL rows."""
    messages = entry.get('messages')
    if not isinstance(messages, list):
        return None

    assistant_blocks = []
    title = ''
    schema_hint = ''

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        role = str(msg.get('role') or '').strip().lower()
        content = str(msg.get('content') or '').strip()
        if not content:
            continue

        if role == 'assistant':
            assistant_blocks.append(content)
            continue

        if role == 'user' and not title:
            title_match = re.match(r'^\s*title\s*:\s*(.+)$', content, flags=re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()
            continue

        if role == 'system' and not schema_hint:
            schema_hint = content

    raw_content = '\n\n'.join(block for block in assistant_blocks if block).strip()
    if not raw_content:
        return None

    return {
        'raw_content': raw_content,
        'title': title,
        'schema_hint': schema_hint,
    }


def _normalize_jsonl_template(
    entry: dict,
    *,
    repo_id: str,
    repo_name: str,
    organization_id: str | None,
    source_branch: str,
    source_path: str,
    line_no: int,
    expected_language: str | None = None,
    language_hint: str | None = None,
    strict_language: bool = STRICT_JSONL_LANGUAGE,
):
    if not isinstance(entry, dict):
        return None

    extracted = _extract_from_chat_messages(entry)

    raw_content = (
        entry.get('query')
        or entry.get('kql')
        or entry.get('eql')
        or entry.get('spl')
        or entry.get('spl_query')
        or entry.get('splunk_query')
        or entry.get('rule')
        or entry.get('rawContent')
        or entry.get('raw_content')
        or entry.get('content')
        or (extracted.get('raw_content') if extracted else None)
    )
    if raw_content is None:
        return None
    content = str(raw_content).strip()
    if not content:
        return None

    title = (
        entry.get('title')
        or entry.get('name')
        or entry.get('rule_name')
        or (extracted.get('title') if extracted else None)
        or os.path.basename(source_path)
    )
    title = str(title).strip()
    description = str(entry.get('description') or '').strip()
    tags = _coerce_tags(entry.get('tags'))
    source_ext = os.path.splitext(source_path)[1].lower()
    explicit_language = _extract_explicit_template_language(entry)
    resolved_expected_language = _normalize_language(expected_language, fallback='')

    if strict_language:
        if resolved_expected_language and explicit_language and explicit_language != resolved_expected_language:
            raise ValueError(
                f"explicit language '{explicit_language}' mismatches dataset language '{resolved_expected_language}'"
            )

        language = explicit_language or resolved_expected_language or _normalize_language(language_hint, fallback='')
        if not language:
            raise ValueError(
                "language is ambiguous; set language/format/rule_format in row or place file under data-kql/data-eql/data-spl"
            )
    else:
        language = _infer_template_language(
            entry,
            source_path=source_path,
            source_ext=source_ext,
            content=content,
            extracted=extracted,
            language_hint=language_hint,
            allow_content_inference=True,
        )

    if not language:
        return None

    source_ref = f"{source_path}:{line_no}"

    schema_context = {
        'mitre': entry.get('mitre'),
        'data_source': entry.get('data_source') or entry.get('datasource'),
        'tactic': entry.get('tactic'),
        'technique': entry.get('technique'),
        'severity': entry.get('severity') or entry.get('level'),
        'system_prompt': (extracted.get('schema_hint') if extracted else None),
    }
    content_hash = _compute_content_hash(
        language=language,
        title=title,
        description=description,
        content=content,
        tags=tags,
        schema_context=schema_context,
    )

    embedding_text = "\n".join(part for part in [title, description, content, ' '.join(tags)] if part)

    return {
        'id': _stable_point_id(repo_id, source_ref),
        'vector_text': embedding_text,
        'payload': {
            'repository_id': str(repo_id),
            'repository_name': repo_name,
            'organization_id': str(organization_id) if organization_id else '',
            'source_path': source_path,
            'source_ref': source_ref,
            'source_branch': source_branch,
            'title': title,
            'description': description,
            'content': content,
            'language': language,
            'tags': tags,
            'schema_version': 'rag-template-v1',
            'schema_context': schema_context,
            'content_hash': content_hash,
            'synced_at': datetime.now(timezone.utc).isoformat(),
        },
    }


def _normalize_json_document_templates(
    raw: str,
    *,
    repo_id: str,
    repo_name: str,
    organization_id: str | None,
    source_branch: str,
    source_path: str,
    expected_language: str | None = None,
    language_hint: str | None = None,
    strict_language: bool = STRICT_JSONL_LANGUAGE,
):
    cleaned_raw = (raw or '').lstrip('\ufeff').strip()
    if not cleaned_raw:
        return [], []

    try:
        parsed_document = json.loads(cleaned_raw)
    except json.JSONDecodeError:
        return [], []

    entries = []
    if isinstance(parsed_document, list):
        entries = parsed_document
    elif isinstance(parsed_document, dict):
        wrapped_entries = (
            parsed_document.get('templates')
            or parsed_document.get('rules')
            or parsed_document.get('items')
        )
        if isinstance(wrapped_entries, list):
            entries = wrapped_entries
        else:
            entries = [parsed_document]
    else:
        return [], []

    normalized_templates = []
    strict_errors = []
    for index, entry in enumerate(entries, start=1):
        try:
            normalized = _normalize_jsonl_template(
                entry,
                repo_id=repo_id,
                repo_name=repo_name,
                organization_id=organization_id,
                source_branch=source_branch,
                source_path=source_path,
                line_no=index,
                expected_language=expected_language,
                language_hint=language_hint,
                strict_language=strict_language,
            )
        except ValueError as exc:
            strict_errors.append(f"Line {index}: {exc}")
            continue
        if normalized:
            normalized_templates.append(normalized)
        elif strict_language:
            strict_errors.append(f"Line {index}: template row did not contain query content")

    return normalized_templates, strict_errors


def _normalize_query_template(
    content: str,
    *,
    repo_id: str,
    repo_name: str,
    organization_id: str | None,
    source_branch: str,
    source_path: str,
    language: str,
):
    cleaned = (content or '').strip()
    if not cleaned:
        return None

    normalized_language = _normalize_language(language)
    comment_prefixes = ['//', '#']

    title = None
    description = ''
    tags = []
    for line in cleaned.splitlines()[:25]:
        line = line.strip()
        matched_prefix = ''
        for prefix in comment_prefixes:
            if line.startswith(prefix):
                matched_prefix = prefix
                break
        if not matched_prefix:
            continue
        text = line[len(matched_prefix):].strip()
        if ':' not in text:
            continue
        key, _, value = text.partition(':')
        key = key.strip().lower()
        value = value.strip()
        if key == 'title' and value:
            title = value
        elif key == 'description' and value:
            description = value
        elif key in {'tags', 'tag'} and value:
            tags = _coerce_tags(value)

    if not title:
        filename = os.path.splitext(os.path.basename(source_path))[0]
        title = filename.replace('_', ' ').replace('-', ' ').title()

    source_ref = source_path
    schema_context = {}
    content_hash = _compute_content_hash(
        language=normalized_language,
        title=title,
        description=description,
        content=cleaned,
        tags=tags,
        schema_context=schema_context,
    )
    embedding_text = "\n".join(part for part in [title, description, cleaned, ' '.join(tags)] if part)

    return {
        'id': _stable_point_id(repo_id, source_ref),
        'vector_text': embedding_text,
        'payload': {
            'repository_id': str(repo_id),
            'repository_name': repo_name,
            'organization_id': str(organization_id) if organization_id else '',
            'source_path': source_path,
            'source_ref': source_ref,
            'source_branch': source_branch,
            'title': title,
            'description': description,
            'content': cleaned,
            'language': normalized_language,
            'tags': tags,
            'schema_version': 'rag-template-v1',
            'schema_context': schema_context,
            'content_hash': content_hash,
            'synced_at': datetime.now(timezone.utc).isoformat(),
        },
    }


def _normalize_kql_template(
    content: str,
    *,
    repo_id: str,
    repo_name: str,
    organization_id: str | None,
    source_branch: str,
    source_path: str,
):
    return _normalize_query_template(
        content,
        repo_id=repo_id,
        repo_name=repo_name,
        organization_id=organization_id,
        source_branch=source_branch,
        source_path=source_path,
        language='KQL',
    )


def _normalize_eql_template(
    content: str,
    *,
    repo_id: str,
    repo_name: str,
    organization_id: str | None,
    source_branch: str,
    source_path: str,
):
    return _normalize_query_template(
        content,
        repo_id=repo_id,
        repo_name=repo_name,
        organization_id=organization_id,
        source_branch=source_branch,
        source_path=source_path,
        language='EQL',
    )


def _normalize_spl_template(
    content: str,
    *,
    repo_id: str,
    repo_name: str,
    organization_id: str | None,
    source_branch: str,
    source_path: str,
):
    return _normalize_query_template(
        content,
        repo_id=repo_id,
        repo_name=repo_name,
        organization_id=organization_id,
        source_branch=source_branch,
        source_path=source_path,
        language='SPL',
    )


def _resolve_dataset_patterns(dataset_path: str | None):
    if dataset_path and dataset_path.strip():
        raw_parts = re.split(r'[\n,;]+', dataset_path)
        parts = [part.strip() for part in raw_parts if part.strip()]
        if parts:
            return parts
    return ['**/*.jsonl', '**/*.kql', '**/*.eql', '**/*.spl']


def _build_file_status(
    source_path: str,
    source_branch: str,
    *,
    language: str,
    ingestion_status: str,
    templates_count: int,
    error_message: str = '',
):
    normalized_language = _normalize_language(language, fallback='') or 'UNKNOWN'
    return {
        'source_path': source_path,
        'source_branch': source_branch,
        'language': normalized_language,
        'ingestion_status': ingestion_status,
        'templates_count': max(int(templates_count or 0), 0),
        'error_message': (error_message or '').strip(),
    }


def collect_templates_from_repo(
    repo_root: str,
    repo_id: str,
    repo_name: str,
    organization_id: str | None,
    source_branch: str,
    dataset_path: str | None,
):
    patterns = _resolve_dataset_patterns(dataset_path)
    candidates = set()
    supported_exts = {'.jsonl', '.kql', '.eql', '.spl'}
    normalizers = {
        '.kql': _normalize_kql_template,
        '.eql': _normalize_eql_template,
        '.spl': _normalize_spl_template,
    }

    for pattern in patterns:
        absolute_pattern = os.path.join(repo_root, pattern)
        for match in glob.glob(absolute_pattern, recursive=True):
            if os.path.isdir(match):
                for ext in ('*.jsonl', '*.kql', '*.eql', '*.spl'):
                    nested = os.path.join(match, '**', ext)
                    for nested_match in glob.glob(nested, recursive=True):
                        if os.path.isfile(nested_match):
                            candidates.add(os.path.abspath(nested_match))
            elif os.path.isfile(match):
                ext = os.path.splitext(match)[1].lower()
                if ext in supported_exts:
                    candidates.add(os.path.abspath(match))

    templates = []
    file_statuses = []
    for file_path in sorted(candidates):
        rel_path = os.path.relpath(file_path, repo_root)
        ext = os.path.splitext(file_path)[1].lower()
        file_language_hint = _language_from_source_path(rel_path, ext=ext)

        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                raw = fh.read()
        except Exception as exc:
            logger.warning("Failed to read template candidate '%s': %s", file_path, exc)
            file_statuses.append(
                _build_file_status(
                    rel_path,
                    source_branch,
                    language=file_language_hint,
                    ingestion_status='FAILED',
                    templates_count=0,
                    error_message=f"Unable to read file: {exc}",
                )
            )
            continue

        if ext == '.jsonl':
            templates_start_index = len(templates)
            raw_without_bom = raw.lstrip('\ufeff')
            parsed_count = 0
            invalid_json_lines = 0
            file_language_counts = {}
            strict_language_errors = []
            for line_no, line in enumerate(raw_without_bom.splitlines(), start=1):
                line_clean = line.strip()
                if not line_clean or line_clean.startswith('#'):
                    continue
                try:
                    entry = json.loads(line_clean)
                except json.JSONDecodeError:
                    logger.debug("Skipping invalid JSONL line %s in %s", line_no, rel_path)
                    invalid_json_lines += 1
                    continue
                try:
                    normalized = _normalize_jsonl_template(
                        entry,
                        repo_id=repo_id,
                        repo_name=repo_name,
                        organization_id=organization_id,
                        source_branch=source_branch,
                        source_path=rel_path,
                        line_no=line_no,
                        expected_language=file_language_hint,
                        language_hint=file_language_hint,
                        strict_language=STRICT_JSONL_LANGUAGE,
                    )
                except ValueError as exc:
                    strict_language_errors.append(f"Line {line_no}: {exc}")
                    continue

                if normalized:
                    templates.append(normalized)
                    parsed_count += 1
                    normalized_language = _normalize_language(
                        (normalized.get('payload') or {}).get('language'),
                        fallback=file_language_hint,
                    ) or 'UNKNOWN'
                    file_language_counts[normalized_language] = file_language_counts.get(normalized_language, 0) + 1
                elif STRICT_JSONL_LANGUAGE:
                    strict_language_errors.append(f"Line {line_no}: template row did not contain query content")

            parsed_with_document_fallback = False
            if parsed_count == 0 and not (STRICT_JSONL_LANGUAGE and strict_language_errors):
                fallback_templates, fallback_strict_errors = _normalize_json_document_templates(
                    raw_without_bom,
                    repo_id=repo_id,
                    repo_name=repo_name,
                    organization_id=organization_id,
                    source_branch=source_branch,
                    source_path=rel_path,
                    expected_language=file_language_hint,
                    language_hint=file_language_hint,
                    strict_language=STRICT_JSONL_LANGUAGE,
                )
                strict_language_errors.extend(fallback_strict_errors)
                if fallback_templates:
                    parsed_with_document_fallback = True
                    templates.extend(fallback_templates)
                    parsed_count = len(fallback_templates)
                    for normalized in fallback_templates:
                        normalized_language = _normalize_language(
                            (normalized.get('payload') or {}).get('language'),
                            fallback=file_language_hint,
                        ) or 'UNKNOWN'
                        file_language_counts[normalized_language] = file_language_counts.get(normalized_language, 0) + 1

            if STRICT_JSONL_LANGUAGE and strict_language_errors:
                del templates[templates_start_index:]
                parsed_count = 0
                file_language_counts = {}

            if parsed_count > 0:
                warning_parts = []
                if parsed_with_document_fallback:
                    warning_parts.append('Parsed as JSON document fallback (non-JSONL format).')
                if invalid_json_lines > 0:
                    warning_parts.append(f"Skipped {invalid_json_lines} invalid JSONL line(s).")
                if strict_language_errors:
                    warning_parts.append(f"Skipped {len(strict_language_errors)} strict-language row(s).")
                warning_message = ' '.join(warning_parts)
                if not file_language_counts:
                    file_language_counts = {
                        _normalize_language(file_language_hint, fallback='') or 'UNKNOWN': parsed_count,
                    }
                for language, templates_count in sorted(file_language_counts.items()):
                    file_statuses.append(
                        _build_file_status(
                            rel_path,
                            source_branch,
                            language=language,
                            ingestion_status='INGESTED',
                            templates_count=templates_count,
                            error_message=warning_message,
                        )
                    )
            else:
                failure_message = 'No valid templates found in JSONL file.'
                if invalid_json_lines > 0:
                    failure_message = f"No valid templates found; {invalid_json_lines} JSONL line(s) were invalid."
                if strict_language_errors:
                    sample_errors = ' | '.join(strict_language_errors[:3])
                    failure_message = (
                        f"Strict language validation failed for {len(strict_language_errors)} row(s). "
                        f"Details: {sample_errors}"
                    )
                file_statuses.append(
                    _build_file_status(
                        rel_path,
                        source_branch,
                        language=file_language_hint or 'UNKNOWN',
                        ingestion_status='FAILED',
                        templates_count=0,
                        error_message=failure_message,
                    )
                )
        elif ext in normalizers:
            normalized = normalizers[ext](
                raw,
                repo_id=repo_id,
                repo_name=repo_name,
                organization_id=organization_id,
                source_branch=source_branch,
                source_path=rel_path,
            )
            language_label = _normalize_language(
                (normalized.get('payload') or {}).get('language') if normalized else file_language_hint,
                fallback=file_language_hint,
            )
            if normalized:
                templates.append(normalized)
                file_statuses.append(
                    _build_file_status(
                        rel_path,
                        source_branch,
                        language=language_label,
                        ingestion_status='INGESTED',
                        templates_count=1,
                    )
                )
            else:
                file_statuses.append(
                    _build_file_status(
                        rel_path,
                        source_branch,
                        language=language_label,
                        ingestion_status='FAILED',
                        templates_count=0,
                        error_message=f'{language_label} file is empty or could not be normalized.',
                    )
                )

    return templates, file_statuses


class QdrantTemplateStore:
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
            headers=self._headers(),
            json=payload,
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            details = (response.text or '').strip()
            if details:
                raise requests.HTTPError(
                    f"{exc}. Response body: {details[:1000]}",
                    response=response,
                    request=response.request,
                ) from exc
            raise
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

    def _fetch_existing_hashes(self, repo_id: str):
        existing = {}
        offset = None
        while True:
            payload = {
                'limit': 256,
                'with_payload': ['content_hash'],
                'with_vector': False,
                'filter': {
                    'must': [
                        {'key': 'repository_id', 'match': {'value': str(repo_id)}},
                    ]
                },
            }
            if offset is not None:
                payload['offset'] = offset

            result = self._request(
                'POST',
                f"/collections/{self.collection_name}/points/scroll",
                payload,
            )
            points = (result.get('result') or {}).get('points') or []
            for point in points:
                point_id = str(point.get('id'))
                payload_data = point.get('payload') or {}
                existing[point_id] = payload_data.get('content_hash')

            offset = (result.get('result') or {}).get('next_page_offset')
            if offset is None:
                break
        return existing

    def _upsert_points(self, points: list[dict]):
        if not points:
            return
        payload = {'points': points}
        self._request('PUT', f"/collections/{self.collection_name}/points?wait=true", payload)

    def _delete_points(self, point_ids: list[str]):
        if not point_ids:
            return
        payload = {'points': point_ids}
        self._request('POST', f"/collections/{self.collection_name}/points/delete?wait=true", payload)

    def sync_repository_templates(self, repo_id: str, templates: list[dict]):
        self.ensure_collection()
        existing_hashes = self._fetch_existing_hashes(repo_id)

        points_to_upsert = []
        discovered_ids = set()

        for template in templates:
            point_id = str(template['id'])
            payload = template['payload']
            discovered_ids.add(point_id)

            previous_hash = existing_hashes.get(point_id)
            if previous_hash and previous_hash == payload.get('content_hash'):
                continue

            points_to_upsert.append({
                'id': point_id,
                'vector': _hash_embedding(template['vector_text'], self.vector_size),
                'payload': payload,
            })

        stale_ids = [pid for pid in existing_hashes.keys() if pid not in discovered_ids]

        self._upsert_points(points_to_upsert)
        self._delete_points(stale_ids)

        return {
            'total': len(templates),
            'upserted': len(points_to_upsert),
            'deleted': len(stale_ids),
            'skipped': len(templates) - len(points_to_upsert),
        }
