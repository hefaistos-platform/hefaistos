"""
OpenTide ``Configurations/schema.toml`` Vocabulary Manager
===========================================================

Provides helpers for reading and writing vocabulary entries in an InitTide /
OpenTide-TOS repository's ``Configurations/schema.toml`` file.

The schema.toml format for custom vocabulary entries is::

    [[vocabulary.log_sources]]
    id = "a1b2c3d4-e5f6-4a12-b345-c6d7e8f90123"
    name = "mde::DeviceEvents"
    description = "Microsoft Defender for Endpoint advanced hunting telemetry"
    "tide.vocab.stages" = "Execution"

    [[vocabulary.surface]]
    id = "b2c3d4e5-f6a7-4b12-c345-d6e7f8a90123"
    name = "host::Windows::MDE"
    description = "Windows Endpoints monitored by Defender for Endpoint"
    "tide.vocab.stages" = "Execution"

The HEFAISTOS ShareTideIndexEntry category names map to schema.toml vocabulary
table names as follows:

    dom_log_sources  →  vocabulary.log_sources
    tvm_surface      →  vocabulary.surface
    tvm_leverage     →  vocabulary.categories
    tvm_impact       →  vocabulary.impact
    tvm_viability    →  vocabulary.viability
    dom_methodologies → vocabulary.methodologies
"""

import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category ↔ TOML table key mapping
# ---------------------------------------------------------------------------

CATEGORY_TO_TOML_KEY: Dict[str, str] = {
    'dom_log_sources': 'log_sources',
    'tvm_surface': 'surface',
    'tvm_leverage': 'categories',
    'tvm_impact': 'impact',
    'tvm_viability': 'viability',
    'dom_methodologies': 'methodologies',
}

TOML_KEY_TO_CATEGORY: Dict[str, str] = {v: k for k, v in CATEGORY_TO_TOML_KEY.items()}

# Default stage tag added to generated TOML entries
_DEFAULT_STAGE = 'Execution'


# ---------------------------------------------------------------------------
# TOML reading
# ---------------------------------------------------------------------------

def _load_toml(path: str) -> Dict[str, Any]:
    """Load a TOML file and return a dict.  Uses ``tomllib`` (3.11+) or ``tomli``."""
    try:
        import tomllib  # Python 3.11+ stdlib
        with open(path, 'rb') as fh:
            return tomllib.load(fh)
    except ImportError:
        pass
    try:
        import tomli  # type: ignore
        with open(path, 'rb') as fh:
            return tomli.load(fh)
    except ImportError:
        pass
    # Minimal fallback: parse [[vocabulary.*]] sections manually
    return _parse_toml_minimal(path)


def _parse_toml_minimal(path: str) -> Dict[str, Any]:
    """Very small TOML parser that handles only the ``[[vocabulary.*]]`` array-of-tables
    pattern used in ``Configurations/schema.toml``.  This is a fallback for environments
    where neither ``tomllib`` nor ``tomli`` is available.
    """
    data: Dict[str, Any] = {'vocabulary': {}}
    vocab = data['vocabulary']

    current_table_key: Optional[str] = None
    current_entry: Optional[Dict[str, Any]] = None

    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.rstrip('\n')
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            # Array-of-tables header: [[vocabulary.log_sources]]
            m = re.match(r'^\[\[vocabulary\.(\w+)\]\]$', stripped)
            if m:
                if current_table_key is not None and current_entry is not None:
                    vocab.setdefault(current_table_key, []).append(current_entry)
                current_table_key = m.group(1)
                current_entry = {}
                continue

            # Key-value pair inside a table entry
            if current_entry is not None:
                kv = re.match(r'^"?([^"=]+)"?\s*=\s*"(.+)"$', stripped)
                if kv:
                    key, value = kv.group(1).strip(), kv.group(2)
                    current_entry[key] = value

    # Flush last entry
    if current_table_key is not None and current_entry is not None:
        vocab.setdefault(current_table_key, []).append(current_entry)

    return data


def read_vocab_from_schema_toml(path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Read vocabulary entries from a ``Configurations/schema.toml`` file.

    Returns a dict keyed by **ShareTideIndexEntry category name** (e.g.
    ``'dom_log_sources'``) with lists of entry dicts containing at least
    ``id``, ``name`` and ``description`` keys.

    Unknown ``vocabulary.*`` keys are preserved under their original key name
    prefixed with ``custom::`` so callers can inspect them.

    Args:
        path: Absolute or relative path to the ``schema.toml`` file.

    Returns:
        dict: ``{category: [{"id": ..., "name": ..., "description": ...}, ...]}``

    Raises:
        FileNotFoundError: When *path* does not exist.
        ValueError: When the file cannot be parsed.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"schema.toml not found: {path}")

    try:
        data = _load_toml(path)
    except Exception as exc:
        raise ValueError(f"Failed to parse schema.toml at {path}: {exc}") from exc

    vocab_section = data.get('vocabulary', {})
    result: Dict[str, List[Dict[str, Any]]] = {}

    for toml_key, entries in vocab_section.items():
        if not isinstance(entries, list):
            continue
        category = TOML_KEY_TO_CATEGORY.get(toml_key, f'custom::{toml_key}')
        parsed: List[Dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            parsed.append({
                'id': entry.get('id', ''),
                'name': entry.get('name', ''),
                'description': entry.get('description', ''),
                'stage': entry.get('tide.vocab.stages', _DEFAULT_STAGE),
            })
        if parsed:
            result[category] = parsed

    return result


# ---------------------------------------------------------------------------
# TOML writing
# ---------------------------------------------------------------------------

def _toml_entry_lines(toml_key: str, entry: Dict[str, Any]) -> List[str]:
    """Return the TOML lines for a single ``[[vocabulary.<key>]]`` entry."""
    entry_id = entry.get('id') or str(uuid.uuid4())
    name = entry.get('name', '')
    description = entry.get('description', '')
    stage = entry.get('stage', _DEFAULT_STAGE)

    def _escape(s: str) -> str:
        return s.replace('\\', '\\\\').replace('"', '\\"')

    return [
        f'[[vocabulary.{toml_key}]]',
        f'id = "{_escape(entry_id)}"',
        f'name = "{_escape(name)}"',
        f'description = "{_escape(description)}"',
        f'"tide.vocab.stages" = "{_escape(stage)}"',
        '',
    ]


def generate_schema_toml(
    entries_by_category: Dict[str, List[Dict[str, Any]]],
    header_comment: str = '',
) -> str:
    """Generate the full text content of a ``Configurations/schema.toml`` file.

    Args:
        entries_by_category: Dict mapping ShareTideIndexEntry category names to
            lists of entry dicts (``id``, ``name``, ``description``, optional
            ``stage``).
        header_comment: Optional comment block to prepend (without ``#`` prefix;
            each line is automatically prefixed).

    Returns:
        str: TOML file content.
    """
    lines: List[str] = []
    if header_comment:
        for comment_line in header_comment.splitlines():
            lines.append(f'# {comment_line}' if comment_line.strip() else '#')
        lines.append('')

    for category, entries in entries_by_category.items():
        toml_key = CATEGORY_TO_TOML_KEY.get(category)
        if not toml_key:
            # Preserve unknown categories under their original key
            toml_key = category.removeprefix('custom::')

        for entry in entries:
            lines.extend(_toml_entry_lines(toml_key, entry))

    return '\n'.join(lines)


def write_vocab_to_schema_toml(
    path: str,
    entries_by_category: Dict[str, List[Dict[str, Any]]],
    merge: bool = True,
) -> None:
    """Write (or merge) vocabulary entries into a ``Configurations/schema.toml`` file.

    When *merge* is True (default) the function reads the existing file first and
    adds only entries whose ``name`` value is not already present, so that
    hand-crafted customisations are preserved.

    When *merge* is False the file is overwritten with exactly the provided
    entries.

    Args:
        path: Absolute path to the ``schema.toml`` file (will be created if absent).
        entries_by_category: Dict mapping category names to entry lists.
        merge: When True, merge new entries into the existing file.
    """
    existing_by_category: Dict[str, List[Dict[str, Any]]] = {}
    if merge and os.path.exists(path):
        try:
            existing_by_category = read_vocab_from_schema_toml(path)
        except Exception as exc:
            logger.warning("Could not read existing schema.toml for merge at %s: %s", path, exc)

    merged: Dict[str, List[Dict[str, Any]]] = {}
    all_categories = set(existing_by_category) | set(entries_by_category)

    for category in all_categories:
        existing = existing_by_category.get(category, [])
        new = entries_by_category.get(category, [])
        existing_names = {e['name'] for e in existing}
        combined = list(existing)
        for entry in new:
            if entry.get('name') and entry['name'] not in existing_names:
                combined.append(entry)
                existing_names.add(entry['name'])
        if combined:
            merged[category] = combined

    header = (
        'Configurations/schema.toml — OpenTide instance vocabulary extensions\n'
        'Generated by HEFAISTOS.  Add custom log sources, surface targets, and\n'
        'other vocabulary entries below.  See the OpenTide documentation for the\n'
        'full list of supported [[vocabulary.*]] table types.'
    )
    content = generate_schema_toml(merged, header_comment=header)

    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(content)
    logger.info("Wrote schema.toml vocabulary to %s (%d categories)", path, len(merged))


# ---------------------------------------------------------------------------
# ShareTideIndexEntry ↔ schema.toml conversion helpers
# ---------------------------------------------------------------------------

def sharetide_entries_to_toml_entries(
    category: str,
    db_entries: List[Any],  # ShareTideIndexEntry queryset or list
) -> List[Dict[str, Any]]:
    """Convert ShareTideIndexEntry ORM objects to schema.toml entry dicts.

    Args:
        category: ShareTideIndexEntry category name.
        db_entries: Iterable of ShareTideIndexEntry instances with ``value``,
            ``description`` and optionally ``id`` attributes.

    Returns:
        list: Entry dicts suitable for :func:`generate_schema_toml`.
    """
    result = []
    for entry in db_entries:
        entry_id = str(getattr(entry, 'id', '') or uuid.uuid4())
        result.append({
            'id': entry_id,
            'name': str(entry.value),
            'description': str(getattr(entry, 'description', '') or ''),
            'stage': _DEFAULT_STAGE,
        })
    return result
