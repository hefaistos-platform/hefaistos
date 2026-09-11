"""
OpenTide Metadata Compiler

Utilities for compiling HEFAISTOS workbench data into OpenTide YAML metadata structure
and the three OpenTIDE object types: TVM, DOM, MDR.

Object folder conventions used when committing to the InitTide repository:
- Threat Vector Models (TVM): ``Objects/Threat Vectors/<id>.yaml``
- Detection Objective Models (DOM): ``Objects/Detection Objectives/<id>.yaml``
- Managed Detection Rules (MDR): ``Objects/Detection Rules/<id>.yaml``
"""

import hashlib
import re
import logging
import uuid
import yaml
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from playbooks.l1_portal import (
    build_l1_portal_share_url,
    upsert_l1_portal_snapshot,
)

logger = logging.getLogger(__name__)


def _str_representer(dumper: yaml.Dumper, data: str) -> yaml.ScalarNode:
    """Use literal block style (``|``) for multiline strings, plain style otherwise.

    Trailing whitespace is stripped from each line so that PyYAML can honour the
    literal block style (``|``) – PyYAML falls back to double-quoted style when
    any line contains trailing whitespace.  Stripping is safe for all supported
    query languages (KQL, SPL, Sigma, WAZUH) where trailing spaces are insignificant.
    Multiple trailing newlines are normalised to a single one, which is also
    inconsequential for all supported query formats.
    """
    if '\n' in data:
        cleaned = '\n'.join(line.rstrip() for line in data.splitlines())
        if data.endswith('\n'):
            cleaned += '\n'
        return dumper.represent_scalar('tag:yaml.org,2002:str', cleaned, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


class _LiteralDumper(yaml.SafeDumper):
    """SafeDumper subclass that renders multiline strings as YAML literal blocks."""


_LiteralDumper.add_representer(str, _str_representer)


def _deterministic_uuid4(namespace: Any, name: str) -> str:
    """Generate a deterministic UUID v4-formatted identifier.

    Produces a stable UUID derived from *namespace* and *name* using SHA-256
    hashing, then forces version bits to 4 and variant bits to RFC 4122 (``10xx``)
    so that the result is indistinguishable from a genuine UUID v4.

    This satisfies OpenTIDE CoreTide validators that require strict UUID v4 format
    while still being idempotent — the same inputs always yield the same output.

    Args:
        namespace: A value whose string representation acts as a namespace
            (e.g. the playbook primary-key UUID).
        name: A short discriminator string (e.g. ``'tvm'``, ``'dom'``, ``'mdr'``).

    Returns:
        str: A UUID v4-format string.
    """
    digest = hashlib.sha256(f"{namespace}:{name}".encode()).digest()
    b = bytearray(digest[:16])
    # Force version nibble to 4
    b[6] = (b[6] & 0x0F) | 0x40
    # Force variant bits to RFC 4122 (10xx)
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


def dump_opentide_yaml(data: Dict[str, Any]) -> str:
    """
    Serialise an OpenTIDE data dict to a YAML string.

    Multiline values (e.g. KQL/SPL queries) are rendered using YAML literal
    block style (``|``) so that the output is human-readable and avoids
    ``\\n`` escape sequences.

    Args:
        data: dict to serialise.

    Returns:
        str: YAML string.
    """
    return yaml.dump(data, Dumper=_LiteralDumper, default_flow_style=False, allow_unicode=True)


def compile_opentide_metadata(playbook) -> Dict[str, Any]:
    """
    Compile OpenTide metadata section from PlaybookGraph instance.

    Args:
        playbook: PlaybookGraph instance

    Returns:
        dict: OpenTide metadata structure
    """
    metadata: Dict[str, Any] = {
        'title': playbook.title or 'Untitled Detection',
        'description': playbook.goal or '',
        'author': playbook.author.username if playbook.author else 'unknown',
        'created': playbook.created_at.isoformat() if playbook.created_at else datetime.utcnow().isoformat(),
        'modified': playbook.updated_at.isoformat() if playbook.updated_at else datetime.utcnow().isoformat(),
    }

    # MITRE ATT&CK mapping
    mitre: Dict[str, Any] = {}
    if playbook.mitre_technique:
        mitre['technique_id'] = playbook.mitre_technique.technique_id
        mitre['technique_name'] = playbook.mitre_technique.name
        if hasattr(playbook.mitre_technique, 'tactic') and playbook.mitre_technique.tactic:
            mitre['tactic'] = playbook.mitre_technique.tactic

    if mitre:
        metadata['mitre'] = mitre

    # Capability abstraction
    capability: Dict[str, Any] = {}
    if playbook.goal:
        capability['goal'] = playbook.goal
    if playbook.technical_context:
        capability['technical_context'] = playbook.technical_context
    if playbook.blind_spots:
        capability['blind_spots'] = playbook.blind_spots
    if playbook.false_positives:
        capability['false_positives'] = playbook.false_positives
    capability_abstractions = []
    selected_caps = getattr(playbook, 'selected_capability_abstractions', None)
    if selected_caps is not None and hasattr(selected_caps, 'all'):
        try:
            for capability_entry in selected_caps.all():
                capability_abstractions.append({
                    'layer': capability_entry.abstraction_layer,
                    'component_artifact': capability_entry.component_artifact,
                    'detection_value': capability_entry.detection_value,
                    'robustness_level': capability_entry.robustness_level,
                })
        except Exception:
            capability_abstractions = []
    if capability_abstractions:
        capability['abstractions'] = capability_abstractions
    detection_focus_layer = getattr(playbook, 'detection_focus_layer', '')
    if isinstance(detection_focus_layer, str) and detection_focus_layer:
        capability['detection_focus_layer'] = detection_focus_layer

    if capability:
        metadata['capability'] = capability

    # Response playbook
    response: Dict[str, Any] = {}
    if playbook.response_playbook:
        response['playbook'] = playbook.response_playbook
    if playbook.default_severity:
        response['severity'] = playbook.default_severity
    if playbook.alert_trigger:
        response['alert_trigger'] = playbook.alert_trigger

    if response:
        metadata['response'] = response

    # Validation
    validation: Dict[str, Any] = {}
    if playbook.robustness_level is not None and playbook.robustness_level > 0:
        validation['robustness_level'] = playbook.robustness_level
    if playbook.data_source_maturity:
        validation['data_source_maturity'] = playbook.data_source_maturity

    if validation:
        metadata['validation'] = validation

    # Tags (if tags manager exists)
    try:
        if hasattr(playbook, 'tags') and playbook.tags.exists():
            metadata['tags'] = list(playbook.tags.values_list('name', flat=True))
    except (AttributeError, Exception) as exc:
        logger.debug("Could not load tags for playbook %s: %s", playbook.id, exc)

    logger.debug("Compiled OpenTide metadata for playbook %s", playbook.id)

    return metadata


def compile_full_opentide_yaml(playbook) -> Dict[str, Any]:
    """
    Compile complete OpenTide YAML structure from PlaybookGraph.

    Includes metadata section and platforms section.

    Args:
        playbook: PlaybookGraph instance

    Returns:
        dict: Complete OpenTide YAML structure
    """
    opentide_yaml: Dict[str, Any] = {
        'metadata': compile_opentide_metadata(playbook),
        'platforms': {},
    }

    # Preserve existing platform queries
    if playbook.opentide_yaml and isinstance(playbook.opentide_yaml, dict):
        existing_platforms = playbook.opentide_yaml.get('platforms', {})
        if existing_platforms:
            opentide_yaml['platforms'] = existing_platforms

    return opentide_yaml


def merge_metadata_with_platforms(playbook, platforms: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge freshly compiled metadata with existing platform queries.

    Used when updating workbench fields – refreshes metadata but keeps platform queries.

    Args:
        playbook: PlaybookGraph instance
        platforms: Existing platforms dict from opentide_yaml

    Returns:
        dict: Complete OpenTide YAML with updated metadata
    """
    return {
        'metadata': compile_opentide_metadata(playbook),
        'platforms': platforms or {},
    }


def validate_opentide_metadata(metadata: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate OpenTide metadata structure.

    Args:
        metadata: Metadata dict to validate

    Returns:
        tuple: (is_valid: bool, errors: list[str])
    """
    errors: List[str] = []

    # Required fields
    for field in ('title', 'author', 'created'):
        if field not in metadata:
            errors.append(f"Missing required field: {field}")

    # MITRE technique ID format validation
    if 'mitre' in metadata:
        technique_id = metadata['mitre'].get('technique_id')
        if technique_id and not re.match(r'^T\d{4}(\.\d{3})?$', technique_id):
            errors.append(f"Invalid MITRE technique ID format: {technique_id}")

    # Severity validation
    if 'response' in metadata:
        severity = metadata['response'].get('severity')
        if severity:
            valid_severities = {'Critical', 'High', 'Medium', 'Low', 'Informational'}
            if severity not in valid_severities:
                errors.append(
                    f"Invalid severity: {severity}. Must be one of: {', '.join(sorted(valid_severities))}"
                )

    # Robustness level validation
    if 'validation' in metadata:
        level = metadata['validation'].get('robustness_level')
        if level is not None:
            if not isinstance(level, int) or level < 1 or level > 5:
                errors.append(f"Invalid robustness_level: {level}. Must be integer 1-5")

    return (len(errors) == 0, errors)


def diff_metadata(old_metadata: Dict[str, Any], new_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute diff between old and new metadata.

    Useful for showing what changed when workbench fields are updated.

    Args:
        old_metadata: Previous metadata
        new_metadata: New metadata

    Returns:
        dict: Changes with structure {field: {'old': value, 'new': value}}
    """
    changes: Dict[str, Any] = {}

    def compare_nested(old: Any, new: Any, path: str = '') -> None:
        if isinstance(old, dict) and isinstance(new, dict):
            all_keys = set(old.keys()) | set(new.keys())
            for key in all_keys:
                new_path = f"{path}.{key}" if path else key
                compare_nested(old.get(key), new.get(key), new_path)
        else:
            if old != new:
                changes[path] = {'old': old, 'new': new}

    compare_nested(old_metadata, new_metadata)
    return changes


# ---------------------------------------------------------------------------
# OpenTIDE object compilers (TVM / DOM / MDR)
# ---------------------------------------------------------------------------

# Static mapping from internal severity codes to human-readable threat labels
# used in DOM response.severity to avoid unnecessary LLM calls.
SEVERITY_LABEL: Dict[str, str] = {
    'CRITICAL': 'Critical incident',
    'HIGH': 'High-severity incident',
    'MEDIUM': 'Moderate incident',
    'LOW': 'Low-severity incident',
    'INFORMATIONAL': 'Informational event',
}

# Severity mapping for TVM threat.severity — must use valid tvm::2.1 enum values
_SEVERITY_TO_TVM_SEVERITY: Dict[str, str] = {
    'CRITICAL': 'Highly significant incident',
    'HIGH': 'Significant incident',
    'MEDIUM': 'Substantial incident',
    'LOW': 'Moderate incident',
    'INFORMATIONAL': 'Localised incident',
}

# Severity mapping for MDR response.alert_severity (Title Case per CoreTide spec)
_SEVERITY_TO_MDR_ALERT: Dict[str, str] = {
    'CRITICAL': 'Critical',
    'HIGH': 'High',
    'MEDIUM': 'Medium',
    'LOW': 'Low',
    'INFORMATIONAL': 'Informational',
}

# Severity mapping for MDE alert block (no Critical level; maps to High)
_SEVERITY_TO_MDE_ALERT: Dict[str, str] = {
    'CRITICAL': 'High',
    'HIGH': 'High',
    'MEDIUM': 'Medium',
    'LOW': 'Low',
    'INFORMATIONAL': 'Informational',
}

# KQL column names used to infer CoreTide DefenderForEndpoint.ImpactedEntities
# (see OpenTide Schemas/MDR Schema.json and CoreTide models.py ImpactedEntities)
_IE_DEVICE_COLS: Tuple[str, ...] = (
    "DeviceId", "DeviceName", "RemoteDeviceName",
    "TargetDeviceName", "DestinationDeviceName",
)
_IE_USER_COLS: Tuple[str, ...] = (
    "AccountUpn", "FileOwnerUpn",
    "InitiatingProcessAccountUpn", "LastModifyingAccountUpn",
    "TargetAccountUpn",
)
_IE_MAILBOX_COLS: Tuple[str, ...] = (
    "SenderFromAddress", "SenderDisplayName",
    "RecipientEmailAddress", "SenderMailFromAddress",
)

# Pre-compiled word-boundary patterns for each ImpactedEntities column category.
# Using \b ensures that e.g. "AccountUpn" does not match inside
# "InitiatingProcessAccountUpn" (false positive from substring search).
_IE_DEVICE_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = tuple(
    (col, re.compile(r'\b' + re.escape(col) + r'\b')) for col in _IE_DEVICE_COLS
)
_IE_USER_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = tuple(
    (col, re.compile(r'\b' + re.escape(col) + r'\b')) for col in _IE_USER_COLS
)
_IE_MAILBOX_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = tuple(
    (col, re.compile(r'\b' + re.escape(col) + r'\b')) for col in _IE_MAILBOX_COLS
)


def _infer_impacted_entities(kql: Optional[str]) -> Dict[str, str]:
    """Build a CoreTide-compliant ``impacted_entities`` block from a KQL query.

    CoreTide requires ``defender_for_endpoint.impacted_entities`` to contain at
    least one of ``device``, ``mailbox``, or ``user``, each mapped to a specific
    KQL column name (see OpenTide Schemas/MDR Schema.json).

    Strategy: scan the KQL text for the first matching column per slot using
    pre-compiled regex word-boundary patterns (``\\b``) so that a column name
    embedded inside a longer identifier (e.g. ``AccountUpn`` inside
    ``InitiatingProcessAccountUpn``) does not produce a false positive.  If no
    recognised column is found, default to ``device: DeviceName`` — the safest
    choice for endpoint-oriented KQL detections.

    Args:
        kql: Raw KQL query string (may be empty or None).

    Returns:
        Dict[str, str]: Mapping of ``device`` / ``user`` / ``mailbox`` keys to
        column name values.  At least one key is always present.
    """
    ie: Dict[str, str] = {}
    text = kql or ""
    for col, pattern in _IE_DEVICE_PATTERNS:
        if pattern.search(text):
            ie["device"] = col
            break
    for col, pattern in _IE_USER_PATTERNS:
        if pattern.search(text):
            ie["user"] = col
            break
    for col, pattern in _IE_MAILBOX_PATTERNS:
        if pattern.search(text):
            ie["mailbox"] = col
            break
    if not ie:
        ie["device"] = "DeviceName"
    return ie


def _normalize_mdr_impacted_entities(mdr_data: Dict[str, Any]) -> None:
    """Ensure ``configurations.defender_for_endpoint.impacted_entities`` is present.

    CoreTide's ``tide.py`` performs a hard ``pop("impacted_entities")`` when
    loading an MDR and raises ``KeyError`` when the field is absent.  MDR dicts
    that were produced before this field was added (e.g. persisted raw YAML
    overrides from the preview modal) may therefore be missing it.

    This function mutates *mdr_data* **in place** so the caller never needs to
    worry about the origin of the MDR dict (compiled fresh vs. user-edited raw
    YAML).  If ``impacted_entities`` is already present it is left untouched.

    Args:
        mdr_data: MDR YAML dict (as returned by :func:`compile_mdr_yaml`).
    """
    dfe = (mdr_data.get('configurations') or {}).get('defender_for_endpoint')
    if isinstance(dfe, dict) and 'impacted_entities' not in dfe:
        dfe['impacted_entities'] = _infer_impacted_entities(dfe.get('query', ''))


def _to_snake_case(identifier: str) -> str:
    """Convert a hyphenated or mixed-case identifier to snake_case.

    For example ``TVM-T1070`` → ``tvm_t1070``.

    Args:
        identifier: Source string (e.g. a derived TVM/DOM/MDR ID).

    Returns:
        str: Lower-snake-case representation.
    """
    return re.sub(r'[^a-z0-9]+', '_', identifier.lower()).strip('_')


SURFACE_KEYWORD_MAP = [
    # Threat Surface vocabulary using strict domain::Entity formatting.
    # Keywords are matched against technical_context (lowercase).
    # More specific patterns are listed before generic ones to avoid false mappings.
    (['command line', 'commandline', 'cmd.exe', 'powershell', 'shell command',
      'command-line', 'cmdline'], 'host::Command Line'),
    (['process creation', 'process execution', 'process injection',
      'process hollowing', 'process doppelgänging'], 'host::Process'),
    (['cloud account', 'iam role', 'managed identity', 'service principal',
      'azure ad', 'azure active directory', 'entra id', 'aws iam', 'gcp iam'], 'cloud::Account'),
    (['cloud user', 'federated user', 'sso user', 'saml user'], 'cloud::User'),
    (['account credential', 'user account', 'local account', 'domain account',
      'admin account', 'service account', 'privileged account'], 'host::Account'),
    (['user session', 'interactive logon', 'rdp session', 'user profile'], 'host::User'),
    (['ip address', 'network connection', 'remote address', 'source ip',
      'destination ip', 'network traffic', 'firewall', 'proxy', 'dns'], 'network::IP Address'),
    (['hostname', 'device name', 'computer name', 'endpoint', 'workstation',
      'server', 'windows', 'linux', 'macos', 'host'], 'host::Hostname'),
    (['process', 'executable', 'binary', 'dll', 'module'], 'host::Process'),
]


def _extract_threat_surface(technical_context: str) -> List[str]:
    """
    Extract hierarchical threat surface categories from technical context.

    Returns a list of surface strings like ["OS::Windows", "Cloud::Azure"].

    Args:
        technical_context: Free-text technical context from the playbook.

    Returns:
        list: Deduplicated list of surface category strings.
    """
    if not technical_context:
        return []

    context_lower = technical_context.lower()
    surfaces: List[str] = []
    seen: set = set()

    for keywords, surface_category in SURFACE_KEYWORD_MAP:
        if any(kw in context_lower for kw in keywords):
            if surface_category not in seen:
                surfaces.append(surface_category)
                seen.add(surface_category)

    return surfaces


def _get_tlp(playbook) -> str:
    """Return the TLP value from the playbook in lowercase, defaulting to 'amber'.

    OpenTIDE/CoreTide validators require lowercase TLP classification values
    (e.g. ``amber``, ``red``, ``green``, ``clear``, ``amber+strict``).
    """
    tlp = getattr(playbook, 'tlp_classification', None)
    return tlp.lower() if tlp else 'amber'


def _build_author_obj(playbook) -> Optional[str]:
    """Build the OpenTIDE ``metadata.author`` string for a playbook.

    Returns a flat string like ``"username (OrgName)"`` (or just ``"username"``
    when no organisation is available), or ``None`` when the playbook has no
    author.

    CoreTide requires ``metadata.author`` to be a plain string, not a nested
    object.
    """
    if not getattr(playbook, 'author', None):
        return None
    author_str: str = playbook.author.username
    try:
        org_name = (
            playbook.organization.name
            if hasattr(playbook, 'organization') and playbook.organization
            else None
        )
        if org_name:
            author_str = f"{author_str} ({org_name})"
    except AttributeError:
        pass
    return author_str


def _derive_id_from_playbook(playbook, prefix: str) -> str:
    """
    Derive an OpenTIDE object identifier from the playbook's custom ID or title.

    Args:
        playbook: PlaybookGraph instance
        prefix: Object type prefix (e.g. ``'DOM'``, ``'MDR'``).

    Returns:
        str: Identifier in the form ``{prefix}-{slug}``.
    """
    if playbook.custom_id:
        sanitized = re.sub(r'[^A-Za-z0-9]+', '-', playbook.custom_id).strip('-')
        return f'{prefix}-{sanitized}'
    title_part = re.sub(r'[^A-Za-z0-9]+', '-', playbook.title or 'unknown').strip('-')[:40]
    return f'{prefix}-{title_part}'


def _derive_tvm_id(playbook) -> str:
    """Derive a Threat Vector Model identifier from the playbook's MITRE technique."""
    if playbook.mitre_technique:
        sanitized = re.sub(r'[^A-Za-z0-9]+', '-', playbook.mitre_technique.technique_id)
        return f'TVM-{sanitized}'
    return _derive_id_from_playbook(playbook, 'TVM')


def _derive_dom_id(playbook) -> str:
    """Derive a Detection Objective Model identifier from the playbook's custom ID or title."""
    return _derive_id_from_playbook(playbook, 'DOM')


def _derive_mdr_id(playbook) -> str:
    """Derive a Managed Detection Rule identifier from the playbook's custom ID or title."""
    return _derive_id_from_playbook(playbook, 'MDR')


def compile_tvm_yaml(playbook, ai_enrichment: Dict = None) -> Dict[str, Any]:
    """
    Compile a Threat Vector Model (TVM) YAML structure from PlaybookGraph.

    The TVM captures the adversary behaviour / attack path and is stored in
    ``Objects/Threat Vectors/`` in the InitTide repository.

    The top-level ``name`` field is a snake_case identifier derived from the
    playbook's MITRE technique ID or custom ID (e.g. ``tvm_t1070``).

    Args:
        playbook: PlaybookGraph instance
        ai_enrichment: Optional dict of AI-generated threat fields containing
            any of: terrain (str), leverage (list), impact (list),
            viability (str), description (str).  When provided these values
            are written into a structured ``threat`` block.  Falls back to
            raw playbook fields when not provided.

    Returns:
        dict: TVM YAML structure conforming to the CoreTide TVM schema (tvm::2.1)
    """
    tvm_id = _derive_tvm_id(playbook)
    tvm_name = _to_snake_case(tvm_id)

    # ------------------------------------------------------------------
    # metadata block
    # ------------------------------------------------------------------
    metadata: Dict[str, Any] = {
        'uuid': _deterministic_uuid4(playbook.id, 'tvm'),
        'schema': 'tvm::2.1',
        'version': 1,
        'tlp': _get_tlp(playbook),
        'created': (
            playbook.created_at.isoformat()
            if playbook.created_at
            else datetime.utcnow().isoformat()
        ),
        'modified': (
            playbook.updated_at.isoformat()
            if playbook.updated_at
            else datetime.utcnow().isoformat()
        ),
    }

    author_obj = _build_author_obj(playbook)
    if author_obj:
        metadata['author'] = author_obj

    tvm: Dict[str, Any] = {
        'name': tvm_name,
        'metadata': metadata,
    }

    # ------------------------------------------------------------------
    # criticality — mapped from default_severity (WikiTide v2.1 requirement)
    # ------------------------------------------------------------------
    _SEVERITY_TO_CRITICALITY: Dict[str, str] = {
        'CRITICAL': 'Critical',
        'HIGH': 'High',
        'MEDIUM': 'Medium',
        'LOW': 'Low',
        'INFORMATIONAL': 'Low',
    }
    if playbook.default_severity:
        tvm['criticality'] = _SEVERITY_TO_CRITICALITY.get(
            playbook.default_severity.upper(), 'Medium'
        )

    # ------------------------------------------------------------------
    # AI-enriched threat block
    # ------------------------------------------------------------------
    ai = ai_enrichment or {}
    threat: Dict[str, Any] = {}

    # att&ck: always populate from linked MITRE technique (REQUIRED)
    if playbook.mitre_technique:
        threat['att&ck'] = [playbook.mitre_technique.technique_id]
    else:
        threat['att&ck'] = []

    # terrain: prefer AI-inferred, fall back to raw technical_context (REQUIRED)
    threat['terrain'] = ai.get('terrain') or playbook.technical_context or 'Not specified'

    # severity: REQUIRED field — map from playbook severity or default to 'Substantial incident'
    threat['severity'] = _SEVERITY_TO_TVM_SEVERITY.get(
        (playbook.default_severity or 'MEDIUM').upper(), 'Substantial incident'
    )

    # leverage: REQUIRED array — use AI-enriched value or default to empty list
    threat['leverage'] = ai.get('leverage') or []

    # impact: REQUIRED array — use AI-enriched value or default to empty list
    threat['impact'] = ai.get('impact') or []

    # viability: REQUIRED string — use AI-enriched value or default
    threat['viability'] = ai.get('viability') or 'Roughly even chance'

    # description: use AI-enriched value or fall back to goal/title
    threat['description'] = ai.get('description') or playbook.goal or playbook.title or 'Not specified'

    # surface: manual overrides take precedence; auto-extracted entries fill in any gaps
    manual_surfaces = getattr(playbook, 'threat_surface', None)
    auto_surfaces = _extract_threat_surface(playbook.technical_context or '')
    if manual_surfaces and isinstance(manual_surfaces, list) and manual_surfaces:
        # Merge: manual first, then auto-detected entries not already present
        merged: List[str] = list(manual_surfaces)
        seen_surfaces: set = set(manual_surfaces)
        for s in auto_surfaces:
            if s not in seen_surfaces:
                merged.append(s)
                seen_surfaces.add(s)
        threat['surface'] = merged
    elif auto_surfaces:
        threat['surface'] = auto_surfaces

    # threat actors: structured attribution data using ATT&CK Group IDs or custom names
    threat_actors = getattr(playbook, 'threat_actors', None)
    if threat_actors and isinstance(threat_actors, list):
        actors_list: List[str] = []
        for actor_data in threat_actors:
            if isinstance(actor_data, dict):
                group_id = actor_data.get('group_id') or actor_data.get('att_ck_id') or actor_data.get('attck_id')
                if group_id:
                    # Prefer canonical ATT&CK Group reference
                    actors_list.append(f'att&ck::{group_id}')
                else:
                    # Fall back to custom:: namespace for non-ATT&CK actors
                    name = (actor_data.get('name') or '').strip()
                    if name:
                        actors_list.append(f'custom::{name}')
        if actors_list:
            threat['actors'] = actors_list

    tvm['threat'] = threat

    # ------------------------------------------------------------------
    # references block — public and internal
    # ------------------------------------------------------------------
    references: Dict[str, Any] = {}

    public_refs = getattr(playbook, 'public_references', None)
    if public_refs and isinstance(public_refs, list) and public_refs:
        references['public'] = {
            str(idx + 1): ref
            for idx, ref in enumerate(public_refs)
        }

    internal_refs = getattr(playbook, 'internal_references', None)
    if internal_refs and isinstance(internal_refs, list) and internal_refs:
        references['internal'] = {
            chr(97 + idx): ref  # 'a', 'b', 'c', ...
            for idx, ref in enumerate(internal_refs)
        }

    if references:
        tvm['references'] = references

    logger.debug("Compiled TVM YAML for playbook %s (%s)", playbook.id, tvm_name)
    return tvm


def compile_dom_yaml(playbook, ai_enrichment: Dict = None) -> Dict[str, Any]:
    """
    Compile a Detection Objective Model (DOM) YAML structure from PlaybookGraph.

    The DOM is a platform-agnostic blueprint that links the threat (TVM) to the
    actual rule (MDR). Stored in ``Objects/Detection Objectives/``.

    The top-level ``name`` field is a snake_case identifier derived from the
    playbook's custom ID or title (e.g. ``dom_de_t1070_001``).

    Args:
        playbook: PlaybookGraph instance
        ai_enrichment: Optional dict of AI-generated threat fields (see
            ``compile_tvm_yaml`` for the full key set).  Currently used to
            derive the human-readable severity label when present.

    Returns:
        dict: DOM YAML structure conforming to the CoreTide DOM schema (dom::2.1)
    """
    dom_id = _derive_dom_id(playbook)
    tvm_id = _derive_tvm_id(playbook)
    dom_name = _to_snake_case(dom_id)

    # ------------------------------------------------------------------
    # metadata block
    # ------------------------------------------------------------------
    metadata: Dict[str, Any] = {
        'uuid': _deterministic_uuid4(playbook.id, 'dom'),
        'schema': 'dom::2.1',
        'version': 1,
        'tlp': _get_tlp(playbook),
        'created': (
            playbook.created_at.isoformat()
            if playbook.created_at
            else datetime.utcnow().isoformat()
        ),
        'modified': (
            playbook.updated_at.isoformat()
            if playbook.updated_at
            else datetime.utcnow().isoformat()
        ),
    }

    author_obj = _build_author_obj(playbook)
    if author_obj:
        metadata['author'] = author_obj

    tvm_name = _to_snake_case(tvm_id)

    dom: Dict[str, Any] = {
        'name': dom_name,
        'metadata': metadata,
    }

    if playbook.triage_guidance:
        dom['triage_guidance'] = playbook.triage_guidance

    # NOTE: ``false_positives`` is intentionally NOT emitted at the DOM root.
    # Although prior revisions of the local schema permitted it, the upstream
    # OpenTIDE / CoreTide ``Detection Objective.schema.json`` defines DOM with
    # ``additionalProperties: false`` and does not include ``false_positives``,
    # so emitting it causes strict schema validation to fail with
    # ``Additional properties are not allowed ('false_positives' was unexpected)``.
    # The data still lives on the playbook (``playbook.false_positives``) and
    # is surfaced via the MDR / metadata compilers where the schema permits.

    # ------------------------------------------------------------------
    # signals — inferred from technical_context keywords and linked_rules formats
    # ------------------------------------------------------------------
    signals: List[Dict[str, Any]] = []

    # Keywords in technical_context that map to data sources
    # Log sources use tool::name format required by OpenTIDE DOM schema
    _SIGNAL_KEYWORD_MAP = [
        (['event log', 'windows event', 'evtx', 'winevt'], 'Windows Event Log', 'siem::Windows Security Events'),
        (['sysmon'], 'Sysmon Telemetry', 'siem::Sysmon'),
        (['network', 'netflow', 'dns', 'firewall', 'proxy'], 'Network Telemetry', 'siem::Network Logs'),
        (['process', 'process creation', 'process execution'], 'Process Telemetry', 'siem::Process Events'),
        (['file', 'file system', 'file creation', 'file modification'], 'File System Telemetry', 'siem::File Events'),
        (['registry', 'regedit'], 'Registry Telemetry', 'siem::Registry Events'),
        (['authentication', 'logon', 'login', 'kerberos', 'ntlm'], 'Authentication Telemetry', 'siem::Authentication Events'),
        (['powershell', 'wmi', 'com'], 'Script Engine Telemetry', 'siem::Script Execution Events'),
    ]

    # Entity types associated with each log source — using domain::Entity format
    _DATASOURCE_ENTITIES: Dict[str, List[str]] = {
        'siem::Windows Security Events': ['host::Process', 'host::User', 'host::Hostname'],
        'siem::Sysmon': ['host::Process', 'host::Hostname'],
        'siem::Network Logs': ['network::IP Address', 'host::Hostname'],
        'siem::Process Events': ['host::Process', 'host::Hostname'],
        'siem::File Events': ['host::Process', 'host::Hostname'],
        'siem::Registry Events': ['host::Hostname', 'host::Process'],
        'siem::Authentication Events': ['host::User', 'host::Account', 'host::Hostname'],
        'siem::Script Execution Events': ['host::Process', 'host::Command Line', 'host::Hostname'],
        'siem::Generic SIEM': ['host::Hostname'],
        'mde::Microsoft Defender XDR': ['host::Process', 'host::Hostname'],
        'splunk::Splunk': ['host::Hostname'],
        'wazuh::Wazuh SIEM': ['host::Hostname'],
        'elastic::Elastic SIEM': ['host::Hostname'],
        'qradar::QRadar SIEM': ['host::Hostname'],
    }

    technical_context_lower = (playbook.technical_context or '').lower()
    seen_data_sources: set = set()
    signal_counter = 0
    for keywords, signal_name, data_source in _SIGNAL_KEYWORD_MAP:
        if any(kw in technical_context_lower for kw in keywords):
            if data_source not in seen_data_sources:
                signal_counter += 1
                signals.append({
                    'uuid': _deterministic_uuid4(playbook.id, f'sig-{data_source}'),
                    'id': f"sig-{signal_counter:03d}",
                    'name': signal_name,
                    'description': f'Detection signal for {signal_name}',
                    'severity': 'Medium',
                    'data': {
                        'availability': 'Unknown',
                        'requirements': f'Requires {data_source} telemetry',
                        'logsources': [data_source],
                    },
                    'methodology': 'Behavioural',
                    'entities': _DATASOURCE_ENTITIES.get(data_source, ['Host']),
                })
                seen_data_sources.add(data_source)

    # Add signals for each distinct detection rule format in linked_rules
    # Log sources use tool::name format required by OpenTIDE DOM schema
    _FORMAT_SIGNAL_MAP = {
        'KQL': ('Defender for Endpoint Query', 'mde::Microsoft Defender XDR'),
        'SPL': ('Splunk Search Query', 'splunk::Splunk'),
        'WAZUH': ('Wazuh Rule', 'wazuh::Wazuh SIEM'),
        'ELASTIC': ('Elastic Query', 'elastic::Elastic SIEM'),
        'EQL': ('Elastic EQL Query', 'elastic::Elastic SIEM'),
        'AQL': ('QRadar AQL Query', 'qradar::QRadar SIEM'),
    }
    try:
        rule_formats = set(
            (r.format or '').upper()
            for r in playbook.linked_rules.all()
            if (r.format or '').upper() in _FORMAT_SIGNAL_MAP
        )
        for fmt in sorted(rule_formats):
            sig_name, data_source = _FORMAT_SIGNAL_MAP[fmt]
            if data_source not in seen_data_sources:
                signal_counter += 1
                signals.append({
                    'uuid': _deterministic_uuid4(playbook.id, f'sig-{data_source}'),
                    'id': f"sig-{signal_counter:03d}",
                    'name': sig_name,
                    'description': f'Detection signal for {sig_name}',
                    'severity': 'Medium',
                    'data': {
                        'availability': 'Unknown',
                        'requirements': f'Requires {data_source} telemetry',
                        'logsources': [data_source],
                    },
                    'methodology': 'Behavioural',
                    'entities': _DATASOURCE_ENTITIES.get(data_source, ['Host']),
                })
                seen_data_sources.add(data_source)
    except Exception as exc:
        logger.debug("Could not load linked_rules for DOM signals in playbook %s: %s", playbook.id, exc)

    # ------------------------------------------------------------------
    # objective block — required top-level field per OpenTIDE DOM schema
    # Contains: type, description, priority, composition, signals, threats
    # ------------------------------------------------------------------
    _SEVERITY_TO_PRIORITY: Dict[str, str] = {
        'CRITICAL': 'Critical',
        'HIGH': 'High',
        'MEDIUM': 'Medium',
        'LOW': 'Low',
        'INFORMATIONAL': 'Informational',
    }

    objective: Dict[str, Any] = {
        'type': 'Threat',
    }

    description = (playbook.goal or playbook.title or '').strip()
    if description:
        objective['description'] = description

    if playbook.default_severity:
        severity_key = playbook.default_severity.upper()
        objective['priority'] = _SEVERITY_TO_PRIORITY.get(severity_key, playbook.default_severity)

    num_signals = len(signals)
    if num_signals <= 1:
        composition_strategy = 'Independent'
        composition_desc = (
            'No signals defined - single detection approach expected'
            if num_signals == 0
            else 'Single signal detection - standalone implementation'
        )
    else:
        composition_strategy = 'Combined'
        composition_desc = f'Combined detection using {num_signals} coordinated signals'

    objective['composition'] = {
        'strategy': composition_strategy,
        'description': composition_desc,
    }
    if signals:
        objective['signals'] = signals

    # threats list links DOM to TVM by UUID (dom::2.1 requirement)
    tvm_uuid = _deterministic_uuid4(playbook.id, 'tvm')
    objective['threats'] = [tvm_uuid]

    dom['objective'] = objective

    # ------------------------------------------------------------------
    # validation block — captures user-entered Workbench validation fields
    # (Summiting Pyramid robustness + Maieutic Engine data-source maturity).
    # The DOM example YAML demonstrates these keys at the DOM root.
    # ------------------------------------------------------------------
    validation: Dict[str, Any] = {}
    robustness_level = getattr(playbook, 'robustness_level', None)
    if robustness_level:  # exclude 0 / None
        validation['robustness_level'] = robustness_level
    data_source_maturity = getattr(playbook, 'data_source_maturity', None)
    if data_source_maturity:
        # Map enum values (KERNEL_MODE/USER_MODE/APPLICATION) to the
        # human-readable form used in OpenTIDE examples (Kernel-Mode / etc.).
        _MATURITY_LABEL: Dict[str, str] = {
            'KERNEL_MODE': 'Kernel-Mode',
            'USER_MODE': 'User-Mode',
            'APPLICATION': 'Application',
        }
        validation['data_source_maturity'] = _MATURITY_LABEL.get(
            data_source_maturity, data_source_maturity
        )
    if validation:
        dom['validation'] = validation

    logger.debug("Compiled DOM YAML for playbook %s (%s)", playbook.id, dom_name)
    return dom


def _deduplicate_kql_tags(content: str) -> str:
    """
    Merge multiple ``// tags:`` comment lines in a KQL query into one.

    Collects all tags from every ``// tags:`` line, removes duplicates while
    preserving insertion order, and replaces the group of tag lines with a
    single consolidated ``// tags:`` line positioned where the first one was.

    Args:
        content: Raw KQL query content.

    Returns:
        str: Query content with deduplicated ``// tags:`` lines.
    """
    lines = content.split('\n')
    seen_ordered: List[str] = []
    seen_set: set = set()
    tag_indices: List[int] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r'^//\s*tags\s*:', stripped, re.IGNORECASE):
            tag_indices.append(i)
            _, _, tag_part = stripped.partition(':')
            for tag in tag_part.split(','):
                tag = tag.strip()
                if tag and tag not in seen_set:
                    seen_ordered.append(tag)
                    seen_set.add(tag)

    if len(tag_indices) <= 1:
        return content

    # Preserve indentation of the first tag line
    first_line = lines[tag_indices[0]]
    indent = first_line[: len(first_line) - len(first_line.lstrip())]
    merged = f"{indent}// tags: {', '.join(seen_ordered)}"

    tag_index_set = set(tag_indices)
    new_lines: List[str] = []
    for i, line in enumerate(lines):
        if i == tag_indices[0]:
            new_lines.append(merged)
        elif i in tag_index_set:
            continue  # drop duplicate tag lines
        else:
            new_lines.append(line)

    return '\n'.join(new_lines)


def compile_mdr_yaml(playbook) -> Dict[str, Any]:
    """
    Compile a Managed Detection Rule (MDR) YAML structure from PlaybookGraph.

    The MDR follows the CoreTide/OpenTide MDR schema and is stored in
    ``Objects/Detection Rules/`` in the InitTide repository.

    The top-level ``name`` field is a snake_case identifier derived from the
    playbook's custom ID or title slug (e.g. ``mdr_de_t1070_001``).
    The filename used when committing is derived separately by the caller from
    the workbench title (``<title>_mdr.yaml``), not from this internal ``name``.

    Detection content is sourced from the actual ``DetectionRule`` objects saved
    to the Detection Library and linked to this playbook via
    ``playbook.linked_rules`` (``DetectionRule.playbook`` FK).  For each
    supported format (KQL, SPL, WAZUH) the most-recently-updated rule is
    used.  Each format is mapped to the corresponding CoreTide system key inside
    the ``configurations`` block:

    - KQL  → ``configurations.defender_for_endpoint`` and ``configurations.microsoft_sentinel``
    - SPL  → ``configurations.splunk``
    - WAZUH → ``configurations.wazuh``

    Args:
        playbook: PlaybookGraph instance

    Returns:
        dict: MDR YAML structure conforming to the CoreTide MDR schema
    """
    mdr_id = _derive_mdr_id(playbook)

    mdr_name = _to_snake_case(mdr_id)

    # ------------------------------------------------------------------
    # metadata block
    # ------------------------------------------------------------------
    metadata: Dict[str, Any] = {
        'uuid': _deterministic_uuid4(playbook.id, 'mdr'),
        'schema': 'mdr::2.1',
        'version': 1,
        'tlp': _get_tlp(playbook),
        'created': (
            playbook.created_at.isoformat()
            if playbook.created_at
            else datetime.utcnow().isoformat()
        ),
        'modified': (
            playbook.updated_at.isoformat()
            if playbook.updated_at
            else datetime.utcnow().isoformat()
        ),
    }

    author_obj = _build_author_obj(playbook)
    if author_obj:
        metadata['author'] = author_obj

    mdr: Dict[str, Any] = {
        'name': mdr_name,
        'metadata': metadata,
    }

    # ------------------------------------------------------------------
    # description
    # ------------------------------------------------------------------
    description = (playbook.goal or playbook.title or '').strip()
    if description:
        mdr['description'] = description

    # ------------------------------------------------------------------
    # response block — REQUIRED top-level field per CoreTide MDR schema
    #
    # Rich response metadata is sourced verbatim from the Workbench Deep Dive /
    # SOAR Configuration sections so user-entered context survives the
    # round-trip to OpenTIDE.  The strict upstream DOM schema rejects
    # ``false_positives`` at the DOM root, so it lives here on MDR (whose
    # schema permits ``additionalProperties: true``).
    # ------------------------------------------------------------------
    response: Dict[str, Any] = {}
    # alert_severity is REQUIRED within response block (uppercase per CoreTide spec)
    response['alert_severity'] = _SEVERITY_TO_MDR_ALERT.get(
        (playbook.default_severity or 'MEDIUM').upper(), 'MEDIUM'
    )

    # Free-text response playbook authored in the Workbench Deep Dive
    response_playbook = getattr(playbook, 'response_playbook', None)
    if response_playbook:
        response['playbook'] = response_playbook

    # Alert trigger description from the Workbench SOAR Configuration
    alert_trigger = getattr(playbook, 'alert_trigger', None)
    if alert_trigger:
        response['alert_trigger'] = alert_trigger

    # Known false positives — captured here (not on DOM root) so strict
    # upstream OpenTIDE validation accepts the object.
    false_positives_text = getattr(playbook, 'false_positives', None)
    if false_positives_text:
        response['false_positives'] = false_positives_text

    # Triage guidance is also surfaced on the MDR response so analysts
    # encountering the rule see it without having to consult the DOM.
    triage_guidance_text = getattr(playbook, 'triage_guidance', None)
    if triage_guidance_text:
        response['triage_guidance'] = triage_guidance_text

    # L1 portal link for downstream SOAR/Ticketing automation.
    # Added only for DEPLOYED workbenches because L1 entries are valid there.
    try:
        if (getattr(playbook, 'status', '') or '').upper() == 'DEPLOYED':
            l1_entry = upsert_l1_portal_snapshot(playbook)
            if l1_entry:
                response['l1_portal_url'] = build_l1_portal_share_url(l1_entry.url_token)
                response['l1_portal_token'] = str(l1_entry.url_token)
    except Exception as exc:
        logger.warning(
            "Could not attach L1 portal response fields for playbook %s: %s",
            getattr(playbook, 'id', 'unknown'),
            exc,
        )

    # Workbench Testing tab — preserve scenario & expected output verbatim.
    # Nested inside ``response`` (rather than a top-level ``testing`` block)
    # because the strict CoreTide MDR schema rejects unknown root keys.
    test_scenario = getattr(playbook, 'test_scenario', None)
    test_expected_output = getattr(playbook, 'test_expected_output', None)
    if test_scenario or test_expected_output:
        testing_block: Dict[str, Any] = {}
        if test_scenario:
            testing_block['scenario'] = test_scenario
        if test_expected_output:
            testing_block['expected_output'] = test_expected_output
        response['testing'] = testing_block

    # procedure: map user-entered enrichment, containment and notification steps
    procedure: Dict[str, Any] = {}
    enrichment_steps = getattr(playbook, 'enrichment_steps', None)
    if enrichment_steps and isinstance(enrichment_steps, list) and enrichment_steps:
        procedure['analysis'] = enrichment_steps
    containment_steps = getattr(playbook, 'containment_steps', None)
    if containment_steps and isinstance(containment_steps, list) and containment_steps:
        procedure['containment'] = containment_steps
    notification_steps = getattr(playbook, 'notification_steps', None)
    if notification_steps and isinstance(notification_steps, list) and notification_steps:
        procedure['notification'] = notification_steps
    if procedure:
        response['procedure'] = procedure
    # response block is REQUIRED, always include it
    mdr['response'] = response

    # ------------------------------------------------------------------
    # configurations block — platform-specific detection queries
    # ------------------------------------------------------------------
    format_to_rule: Dict[str, Any] = {}
    try:
        for rule in playbook.linked_rules.order_by('format', '-updated_at'):
            fmt = (rule.format or '').upper()
            if fmt not in format_to_rule:
                format_to_rule[fmt] = rule
    except Exception as exc:
        logger.warning(
            "Could not load linked_rules for playbook %s: %s", playbook.id, exc
        )

    configurations: Dict[str, Any] = {}

    kql_rule = format_to_rule.get('KQL')
    if kql_rule and (kql_rule.raw_content or '').strip():
        kql_content = _deduplicate_kql_tags(kql_rule.raw_content.strip())

        # Build alert block conforming to CoreTide DefenderForEndpoint.Alert schema
        alert_block: Dict[str, Any] = {
            'category': 'Suspicious Activity',  # Required field; default category
        }

        if playbook.title:
            alert_block['title'] = playbook.title

        if playbook.goal:
            alert_block['description'] = playbook.goal

        if playbook.default_severity:
            alert_block['severity'] = _SEVERITY_TO_MDE_ALERT.get(
                playbook.default_severity.upper(), 'Medium'
            )

        if hasattr(playbook, 'triage_guidance') and playbook.triage_guidance:
            alert_block['recommendation'] = playbook.triage_guidance

        if playbook.mitre_technique:
            technique_id = playbook.mitre_technique.technique_id
            if technique_id:
                alert_block['techniques'] = [technique_id]

        configurations['defender_for_endpoint'] = {
            'schema': 'defender_for_endpoint::2.0',
            'status': 'PRODUCTION',
            'scheduling': '1H',
            'query': kql_content,
            'alert': alert_block,
            'impacted_entities': _infer_impacted_entities(kql_content),
            'scope': {
                'selection': 'All',
            },
        }
        configurations['microsoft_sentinel'] = {
            'schema': 'microsoft_sentinel::1.0',
            'status': 'PRODUCTION',
            'query': kql_content,
            'queryFrequency': 'PT5H',
            'queryPeriod': 'P1D',
            'triggerOperator': 'GreaterThan',
            'triggerThreshold': 0,
            'suppressionDuration': 'PT1H',
            'suppressionEnabled': False,
        }

    spl_rule = format_to_rule.get('SPL')
    if spl_rule and (spl_rule.raw_content or '').strip():
        configurations['splunk'] = {'query': spl_rule.raw_content.strip()}

    wazuh_rule = format_to_rule.get('WAZUH')
    if wazuh_rule and (wazuh_rule.raw_content or '').strip():
        configurations['wazuh'] = {'rule': wazuh_rule.raw_content.strip()}

    elastic_rule = format_to_rule.get('ELASTIC') or format_to_rule.get('EQL')
    if elastic_rule and (elastic_rule.raw_content or '').strip():
        configurations['elastic'] = {'query': elastic_rule.raw_content.strip()}

    aql_rule = format_to_rule.get('AQL')
    if aql_rule and (aql_rule.raw_content or '').strip():
        configurations['qradar'] = {'query': aql_rule.raw_content.strip()}

    if configurations:
        mdr['configurations'] = configurations
    else:
        logger.warning(
            "MDR for playbook %s has no configurations. "
            "At least one detection rule (KQL/SPL/WAZUH/ELASTIC/AQL) must be saved.",
            playbook.id,
        )
        mdr['_validation_warning'] = 'No detection configurations present'

    logger.debug("Compiled MDR YAML for playbook %s (%s)", playbook.id, mdr_name)
    return mdr


# ---------------------------------------------------------------------------
# AI-enhanced compiler variants
# ---------------------------------------------------------------------------

def _derive_bdr_name_from_tvm_id(tvm_id: str) -> str:
    """Derive a BDR identifier string from a TVM identifier by replacing the prefix."""
    if tvm_id.startswith('tvm_'):
        return 'bdr_' + tvm_id[4:]
    return f'bdr_{tvm_id}'

def compile_mdr_yaml_with_ai(
    playbook,
    ai_settings=None,
    use_ai_enrichment: bool = True,
) -> Dict[str, Any]:
    """
    Compile an MDR YAML structure, optionally enriched with AI-generated metadata.

    IMPORTANT: Detection rule content (KQL, SPL, Sigma, WAZUH queries) is NEVER
    generated by AI — it always comes from the user's saved DetectionRule objects.
    AI enrichment covers response procedures and platform/target mapping only.

    Args:
        playbook: PlaybookGraph instance.
        ai_settings: UserAISettings (or effective settings) instance, or None.
        use_ai_enrichment: When False behaves identically to compile_mdr_yaml().

    Returns:
        MDR dict.  AI-generated fields are tracked under the ``_ai_generated``
        key (removed before YAML serialisation).
    """
    mdr = compile_mdr_yaml(playbook)
    ai_generated: Dict[str, bool] = {}

    if not use_ai_enrichment or ai_settings is None:
        return mdr

    try:
        from ai_assistant.opentide_enrichment import (
            ai_enrich_mdr_response,
        )

        playbook_data = {
            'title': playbook.title or '',
            'goal': playbook.goal or '',
            'technical_context': playbook.technical_context or '',
            'default_severity': playbook.default_severity or 'MEDIUM',
            'false_positives': playbook.false_positives or '',
            'response_playbook': playbook.response_playbook or '',
        }

        # Enrich response block (analysis, searches, containment)
        if getattr(ai_settings, 'auto_enrich_response', True):
            enriched_response = ai_enrich_mdr_response(playbook_data, ai_settings)
            existing_response = mdr.get('response', {})

            # Merge: AI fills only missing fields; user-supplied fields take precedence
            merged_response = dict(existing_response)
            if not merged_response.get('alert_severity') and enriched_response.get('alert_severity'):
                merged_response['alert_severity'] = enriched_response['alert_severity']
                ai_generated['response.alert_severity'] = True

            if enriched_response.get('responders'):
                merged_response['responders'] = enriched_response['responders']
                ai_generated['response.responders'] = True

            procedure = enriched_response.get('procedure', {})
            if procedure.get('analysis') or procedure.get('searches') or procedure.get('containment'):
                merged_response['procedure'] = procedure
                ai_generated['response.procedure.analysis'] = bool(procedure.get('analysis'))
                ai_generated['response.procedure.searches'] = bool(procedure.get('searches'))
                ai_generated['response.procedure.containment'] = bool(procedure.get('containment'))

            if merged_response:
                mdr['response'] = merged_response

    except Exception as exc:
        logger.warning("AI MDR enrichment failed for playbook %s: %s", playbook.id, exc)

    if ai_generated:
        mdr['_ai_generated'] = ai_generated

    return mdr


def compile_bdr_yaml_with_ai(
    playbook,
    ai_settings=None,
    force_generate: bool = False,
    use_ai_enrichment: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    .. deprecated::
        The Business Detection Rule (BDR) framework has been officially
        deprecated in favour of the Detection Objectives (DOM) framework.
        This function always returns ``None`` and will be removed in a future
        release.  All callers should rely on :func:`compile_dom_yaml_with_ai`
        instead.

    Args:
        playbook: PlaybookGraph instance (unused).
        ai_settings: UserAISettings instance, or None (unused).
        force_generate: Ignored — BDR generation is no longer supported.
        use_ai_enrichment: Ignored.

    Returns:
        Always ``None``.
    """
    logger.debug(
        "compile_bdr_yaml_with_ai called for playbook %s — BDR framework is deprecated; "
        "returning None. Use compile_dom_yaml_with_ai instead.",
        getattr(playbook, 'id', 'unknown'),
    )
    return None


def compile_dom_yaml_with_ai(
    playbook,
    ai_settings=None,
    use_ai_enrichment: bool = True,
) -> Dict[str, Any]:
    """
    Compile a DOM YAML structure, optionally enriched with AI-generated signals.

    Signals are purely descriptive (data sources and observable behaviour) —
    they never contain detection rule logic or queries.

    Args:
        playbook: PlaybookGraph instance.
        ai_settings: UserAISettings instance, or None.
        use_ai_enrichment: When False behaves identically to compile_dom_yaml().

    Returns:
        DOM dict with optional AI-generated signals and _ai_generated tracking.
    """
    dom = compile_dom_yaml(playbook)
    ai_generated: Dict[str, bool] = {}

    if not use_ai_enrichment or ai_settings is None:
        return dom

    try:
        from ai_assistant.opentide_enrichment import ai_generate_detection_objective

        playbook_data = {
            'title': playbook.title or '',
            'goal': playbook.goal or '',
            'technical_context': playbook.technical_context or '',
            'default_severity': playbook.default_severity or 'MEDIUM',
            'false_positives': getattr(playbook, 'false_positives', '') or '',
            'mitre_technique_id': (
                playbook.mitre_technique.technique_id if playbook.mitre_technique else ''
            ),
            'mitre_technique_name': (
                playbook.mitre_technique.name if playbook.mitre_technique else ''
            ),
        }

        objective = ai_generate_detection_objective(playbook_data, ai_settings)

        dom_objective = dom.setdefault('objective', {})

        if objective.get('signals'):
            dom_objective['signals'] = objective['signals']
            ai_generated['signals'] = True

        if objective.get('priority') and 'priority' not in dom_objective:
            dom_objective['priority'] = objective['priority']
            ai_generated['priority'] = True

        # ``false_positives`` is intentionally NOT written to the DOM root: the
        # upstream OpenTIDE Detection Objective schema rejects it as an
        # additional property.  The AI-generated value (if any) is discarded
        # here for DOM compilation purposes; downstream MDR/response enrichment
        # consumes the playbook's own ``false_positives`` field directly.

    except Exception as exc:
        logger.warning("AI DOM enrichment failed for playbook %s: %s", playbook.id, exc)

    if ai_generated:
        dom['_ai_generated'] = ai_generated

    return dom
