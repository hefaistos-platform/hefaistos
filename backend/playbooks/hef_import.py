"""
OpenTIDE HEF Import helpers
===========================
Reverse-import path: discovers OpenTIDE HEF bundles from a GitHub repository,
fetches the YAML files, validates them, and converts them to an in-memory
HEX v2.0 document so that ``deserialize_playbook_graph_hex_v2`` can create a
new PlaybookGraph without a second deserialiser.

Bundle layout expected on GitHub::

    <target_folder>/
        Objects/Threat Vectors/<tvm>.yaml
        Objects/Detection Objectives/<dom>.yaml
        Objects/Detection Rules/<mdr>.yaml          ← required
        Objects/Business Rules/<bdr>.yaml           ← optional
        <kql|splunk|sigma|wazuh|qradar>/            ← optional platform rules

A ``_hef_index.json`` manifest at ``<target_folder>/_hef_index.json`` is used
as a fast-path when present; the worker falls back to full tree-walk otherwise.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import yaml

from playbooks.repo_clients import RepoClient

logger = logging.getLogger(__name__)

# Paths that indicate each bundle type inside a target_folder subtree.
# A bundle directory is valid when it contains at least one of the required
# subdirectory keys.
_REQUIRED_SUBDIRS = {'Objects/Detection Rules'}
_OPTIONAL_SUBDIRS = {'Objects/Threat Vectors', 'Objects/Detection Objectives', 'Objects/Business Rules'}
_PLATFORM_SUBDIRS = {'kql', 'splunk', 'sigma', 'wazuh', 'qradar'}

# Hard cap on bundles per job (overridden by Django setting HEF_IMPORT_MAX_BUNDLES_PER_JOB).
DEFAULT_MAX_BUNDLES = 100


def get_repo_client(
    repo_url: str,
    token: str,
    provider: str = 'AUTO',
    api_base_url: Optional[str] = None,
    verify_ssl: bool = True,
) -> RepoClient:
    return RepoClient(
        repo_url=repo_url,
        token=token,
        provider=provider,
        api_base_url=api_base_url,
        verify_ssl=verify_ssl,
    )


def _build_client(
    *,
    repo_owner: str,
    repo_name: str,
    token: str,
    repo_url: Optional[str] = None,
    provider: str = 'AUTO',
    api_base_url: Optional[str] = None,
    verify_ssl: bool = True,
) -> RepoClient:
    effective_repo_url = repo_url or f'https://github.com/{repo_owner}/{repo_name}'
    return RepoClient(
        repo_url=effective_repo_url,
        token=token,
        provider=provider,
        api_base_url=api_base_url,
        verify_ssl=verify_ssl,
    )


def _resolve_commit_sha(
    repo_owner: str,
    repo_name: str,
    branch: str,
    token: str,
    commit_sha: Optional[str] = None,
    *,
    repo_url: Optional[str] = None,
    provider: str = 'AUTO',
    api_base_url: Optional[str] = None,
    verify_ssl: bool = True,
) -> str:
    """Return the commit SHA to use for tree walking.

    If ``commit_sha`` is provided and non-empty it is returned unchanged.
    Otherwise the HEAD of ``branch`` is resolved via the GitHub API.
    """
    client = _build_client(
        repo_owner=repo_owner,
        repo_name=repo_name,
        token=token,
        repo_url=repo_url,
        provider=provider,
        api_base_url=api_base_url,
        verify_ssl=verify_ssl,
    )
    return client.resolve_commit_sha(branch=branch, commit_sha=commit_sha)


def _fetch_tree(
    repo_owner: str,
    repo_name: str,
    sha: str,
    token: str,
    *,
    repo_url: Optional[str] = None,
    provider: str = 'AUTO',
    api_base_url: Optional[str] = None,
    verify_ssl: bool = True,
) -> List[Dict[str, Any]]:
    """Fetch the recursive git tree for *sha* and return the list of tree items."""
    client = _build_client(
        repo_owner=repo_owner,
        repo_name=repo_name,
        token=token,
        repo_url=repo_url,
        provider=provider,
        api_base_url=api_base_url,
        verify_ssl=verify_ssl,
    )
    return client.fetch_tree(sha)


def discover_hef_bundles(
    repo_owner: str,
    repo_name: str,
    branch: str,
    token: str,
    target_folder: Optional[str] = None,
    commit_sha: Optional[str] = None,
    *,
    repo_url: Optional[str] = None,
    provider: str = 'AUTO',
    api_base_url: Optional[str] = None,
    verify_ssl: bool = True,
) -> Tuple[List[Dict[str, Any]], str]:
    """Discover HEF bundle descriptors in a GitHub repository.

    Attempts to load ``<target_folder>/_hef_index.json`` as a fast-path.
    Falls back to a full recursive tree walk when the index is absent.

    Returns:
        (bundles, resolved_commit_sha) where each bundle dict contains::

            {
                "path": "<mdr_yaml_path>",
                "mdr_title": "<title from metadata.title>",
                "mdr_uuid": "<uuid from metadata.uuid>",
                "status": "<status or empty string>",
                "techniques": ["T1059.001", ...],
                "last_commit": "<commit sha>",
                "files": {
                    "tvm": "<path or None>",
                    "dom": "<path or None>",
                    "mdr": "<path>",
                    "bdr": "<path or None>",
                    "platform_files": {"kql": ["<path>", ...], ...},
                },
                "valid": True,
                "validation_errors": [],
            }
    """
    base_folder = (target_folder or '').strip('/')
    client = _build_client(
        repo_owner=repo_owner,
        repo_name=repo_name,
        token=token,
        repo_url=repo_url,
        provider=provider,
        api_base_url=api_base_url,
        verify_ssl=verify_ssl,
    )
    resolved_sha = client.resolve_commit_sha(branch=branch, commit_sha=commit_sha)

    # --- fast-path: _hef_index.json ---
    index_path = f'{base_folder}/_hef_index.json' if base_folder else '_hef_index.json'
    index_bundles = _try_load_hef_index(client, resolved_sha, index_path)
    if index_bundles is not None:
        logger.info(
            'HEF import: loaded %d bundles from manifest %s@%s',
            len(index_bundles),
            index_path,
            resolved_sha,
        )
        return index_bundles, resolved_sha

    # --- fallback: recursive tree walk ---
    logger.info(
        'HEF import: no manifest found at %s, falling back to tree walk for %s/%s@%s',
        index_path,
        repo_owner,
        repo_name,
        resolved_sha,
    )
    tree_items = client.fetch_tree(resolved_sha)
    bundles = _build_bundle_descriptors_from_tree(tree_items, base_folder, resolved_sha)
    return bundles, resolved_sha


def _try_load_hef_index(
    client: RepoClient,
    commit_sha: str,
    index_path: str,
) -> Optional[List[Dict[str, Any]]]:
    """Try to load and parse ``_hef_index.json``.  Returns None on any failure."""
    content = client.get_file_content(index_path, commit_sha)
    if content is None:
        return None
    try:
        entries = json.loads(content)
        if not isinstance(entries, list):
            return None
        # Convert index entries to bundle descriptors (minimal form; worker will fetch full files)
        bundles = []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get('path'):
                continue
            bundles.append({
                'path': entry['path'],
                'mdr_title': entry.get('title', ''),
                'mdr_uuid': entry.get('mdr_uuid', ''),
                'status': entry.get('status', ''),
                'techniques': entry.get('techniques', []),
                'last_commit': entry.get('last_commit_sha', commit_sha),
                'files': {},   # worker will discover files from paths
                'valid': True,
                'validation_errors': [],
            })
        return bundles if bundles else None
    except Exception as exc:
        logger.warning('HEF import: failed to parse _hef_index.json: %s', exc)
        return None


def _strip_object_suffix(stem: str, object_type: str) -> str:
    """Strip a trailing ``_<object_type>`` suffix from a filename stem."""
    suffix = f'_{object_type.lower()}'
    if stem.lower().endswith(suffix):
        return stem[:-len(suffix)]
    return stem


def _bundle_key_from_stem(stem: str, object_type: str) -> str:
    """
    Build a grouping key that supports both legacy and title-based HEF names.

    New format:
      ``<WorkbenchTitle>_tvm|dom|mdr``  -> shared key: ``<WorkbenchTitle>``

    Legacy format:
      ``mdr_*`` / ``dom_*`` / ``tvm_*`` -> strips role prefix when present.
    """
    base = _strip_object_suffix(stem, object_type)
    legacy_prefix = f'{object_type.lower()}_'
    if base.lower().startswith(legacy_prefix):
        return base[len(legacy_prefix):]
    return base


def _build_bundle_descriptors_from_tree(
    tree_items: List[Dict[str, Any]],
    base_folder: str,
    commit_sha: str,
) -> List[Dict[str, Any]]:
    """Group tree items into HEF bundle descriptors based on directory structure.

    A bundle directory is the *parent folder* of a ``mdr.yaml`` file that lives
    under ``<base_folder>/Objects/Detection Rules/``.
    """
    # Build a quick lookup of path → sha for blob items
    blob_by_path: Dict[str, str] = {
        item['path']: item['sha']
        for item in tree_items
        if item.get('type') == 'blob'
    }

    prefix = (base_folder + '/') if base_folder else ''
    mdr_dir = f'{prefix}Objects/Detection Rules/'
    tvm_dir = f'{prefix}Objects/Threat Vectors/'
    dom_dir = f'{prefix}Objects/Detection Objectives/'
    bdr_dir = f'{prefix}Objects/Business Rules/'

    # Map logical bundle key → {tvm, dom, mdr, bdr, platform_files}
    bundle_map: Dict[str, Dict[str, Any]] = {}

    for path in blob_by_path:
        if path.startswith(mdr_dir) and path.endswith('.yaml'):
            stem = path[len(mdr_dir):].split('.yaml')[0]
            key = _bundle_key_from_stem(stem, 'mdr')
            entry = bundle_map.setdefault(key, {})
            if 'mdr' in entry and entry.get('mdr') != path:
                # Avoid clobbering when two unrelated files normalize to same key.
                key = stem
                entry = bundle_map.setdefault(key, {})
            entry['mdr'] = path
            entry['_mdr_stem'] = stem
        elif path.startswith(tvm_dir) and path.endswith('.yaml'):
            stem = path[len(tvm_dir):].split('.yaml')[0]
            key = _bundle_key_from_stem(stem, 'tvm')
            bundle_map.setdefault(key, {})['tvm'] = path
        elif path.startswith(dom_dir) and path.endswith('.yaml'):
            stem = path[len(dom_dir):].split('.yaml')[0]
            key = _bundle_key_from_stem(stem, 'dom')
            bundle_map.setdefault(key, {})['dom'] = path
        elif path.startswith(bdr_dir) and path.endswith('.yaml'):
            stem = path[len(bdr_dir):].split('.yaml')[0]
            key = _bundle_key_from_stem(stem, 'bdr')
            bundle_map.setdefault(key, {})['bdr'] = path
        else:
            # Platform rule files: <prefix>/<platform>/<filename>
            for plat in _PLATFORM_SUBDIRS:
                plat_dir = f'{prefix}{plat}/'
                if path.startswith(plat_dir):
                    fname = path[len(plat_dir):]
                    # Group by base name without extension
                    stem = fname.rsplit('.', 1)[0]
                    key = _bundle_key_from_stem(stem, 'mdr')
                    bundle_map.setdefault(key, {}).setdefault('platform_files', {}).setdefault(plat, []).append(path)

    bundles = []
    for key, files in bundle_map.items():
        if 'mdr' not in files:
            continue  # not a complete bundle
        mdr_stem = files.get('_mdr_stem') or key
        bundles.append({
            'path': files['mdr'],
            'mdr_title': mdr_stem,
            'mdr_uuid': '',
            'status': '',
            'techniques': [],
            'last_commit': commit_sha,
            'files': {
                'tvm': files.get('tvm'),
                'dom': files.get('dom'),
                'mdr': files['mdr'],
                'bdr': files.get('bdr'),
                'platform_files': files.get('platform_files', {}),
            },
            'valid': True,
            'validation_errors': [],
        })

    return sorted(bundles, key=lambda b: b['path'])


def fetch_bundle_files(
    repo_owner: str,
    repo_name: str,
    token: str,
    file_paths: Dict[str, Optional[str]],
    commit_sha: str,
    *,
    repo_url: Optional[str] = None,
    provider: str = 'AUTO',
    api_base_url: Optional[str] = None,
    verify_ssl: bool = True,
) -> Dict[str, Optional[str]]:
    """Fetch the YAML content of each file path in *file_paths*.

    Args:
        file_paths: mapping of role → path (e.g. ``{"mdr": "Objects/Detection Rules/foo.yaml", ...}``).
                    A value of ``None`` means the file is absent; it is left as ``None``.

    Returns:
        Mapping of role → YAML text (or ``None`` when the path was ``None``).
    """
    result: Dict[str, Optional[str]] = {}
    client = _build_client(
        repo_owner=repo_owner,
        repo_name=repo_name,
        token=token,
        repo_url=repo_url,
        provider=provider,
        api_base_url=api_base_url,
        verify_ssl=verify_ssl,
    )

    for role, path in file_paths.items():
        if path is None:
            result[role] = None
            continue
        result[role] = client.get_file_content(path, commit_sha)

    return result


def bundle_to_hex_v2(bundle_files: Dict[str, Optional[str]], title_override: Optional[str] = None) -> Dict[str, Any]:
    """Convert TVM/DOM/MDR/BDR YAML texts to an in-memory HEX v2.0 document.

    The resulting document is passed to ``deserialize_playbook_graph_hex_v2``
    so we re-use the proven import path instead of writing a second
    deserialiser.

    Args:
        bundle_files: dict with keys ``mdr``, ``tvm``, ``dom``, ``bdr``
                      mapping to YAML text (or ``None`` when absent).
        title_override: optional title to use instead of MDR metadata.title.

    Returns:
        HEX v2.0 dict with ``hex_format`` = ``"2.0"``.
    """
    mdr_text = bundle_files.get('mdr') or ''
    tvm_text = bundle_files.get('tvm') or ''
    dom_text = bundle_files.get('dom') or ''

    mdr: Dict[str, Any] = yaml.safe_load(mdr_text) or {} if mdr_text else {}
    tvm: Dict[str, Any] = yaml.safe_load(tvm_text) or {} if tvm_text else {}
    dom: Dict[str, Any] = yaml.safe_load(dom_text) or {} if dom_text else {}

    # --- metadata ---
    mdr_meta = mdr.get('metadata') or {}
    tvm_meta = tvm.get('metadata') or {}

    mdr_title_field = mdr_meta.get('title') or mdr.get('name') or ''
    title = title_override or mdr_title_field or 'Imported Workbench'

    mdr_uuid = mdr_meta.get('uuid') or ''
    status_raw = (mdr.get('configurations') or {})
    # derive status from any configurations block status field
    rule_status = 'DEVELOPMENT'
    for cfg in status_raw.values():
        if isinstance(cfg, dict) and cfg.get('status'):
            rule_status = cfg['status']
            break

    # --- MITRE techniques from TVM ---
    techniques: List[Dict[str, str]] = []
    tvm_threat = tvm.get('threat') or {}
    attck_list = tvm_threat.get('att&ck') or []
    for tid in attck_list:
        techniques.append({'technique_id': str(tid), 'name': '', 'tactic': ''})

    # --- detection rule from MDR configurations ---
    detection_rule = ''
    configurations = mdr.get('configurations') or {}
    for cfg_key in ('defender_for_endpoint', 'microsoft_sentinel', 'splunk', 'wazuh', 'elastic', 'qradar'):
        cfg_val = configurations.get(cfg_key)
        if cfg_val and isinstance(cfg_val, dict):
            detection_rule = (
                cfg_val.get('query')
                or cfg_val.get('rule')
                or ''
            )
            if detection_rule:
                break

    # --- goal / context from MDR description / DOM objective ---
    goal = mdr.get('description') or dom.get('description') or ''
    dom_objective = dom.get('objective') or {}
    if isinstance(dom_objective, dict):
        goal = goal or dom_objective.get('description') or ''

    tvm_terrain = tvm_threat.get('terrain') or ''
    technical_context = tvm_terrain

    false_positives = ''
    mdr_response = mdr.get('response') or {}
    if isinstance(mdr_response, dict):
        fp = mdr_response.get('false_positives') or ''
        false_positives = fp
        triage_guidance = mdr_response.get('triage_guidance') or ''
        response_playbook = mdr_response.get('playbook') or ''
        alert_severity = mdr_response.get('alert_severity') or 'MEDIUM'
        testing_block = mdr_response.get('testing') or {}
        test_scenario = testing_block.get('scenario') or '' if isinstance(testing_block, dict) else ''
        test_expected_output = testing_block.get('expected_output') or '' if isinstance(testing_block, dict) else ''
    else:
        triage_guidance = ''
        response_playbook = ''
        alert_severity = 'MEDIUM'
        test_scenario = ''
        test_expected_output = ''

    # --- graph nodes: minimal single-node representation ---
    # We create a thin 3-node graph: TVM node → DOM node → MDR node
    # This mirrors the conceptual layers without rebuilding the full visual graph.
    nodes = []
    edges = []

    tvm_node_id = 'n-tvm'
    dom_node_id = 'n-dom'
    mdr_node_id = 'n-mdr'

    tvm_label = tvm.get('name') or 'Threat Vector'
    dom_label = dom.get('name') or 'Detection Objective'
    mdr_label = mdr.get('name') or title

    nodes.append({'id': tvm_node_id, 'layer_name': tvm_label, 'position_x': 50, 'position_y': 50})
    nodes.append({'id': dom_node_id, 'layer_name': dom_label, 'position_x': 50, 'position_y': 200})
    nodes.append({'id': mdr_node_id, 'layer_name': mdr_label, 'position_x': 50, 'position_y': 350})
    edges.append({'source': tvm_node_id, 'target': dom_node_id})
    edges.append({'source': dom_node_id, 'target': mdr_node_id})

    hex_doc = {
        'hex_format': '2.0',
        'metadata': {
            'name': title,
            'description': goal,
            'version': '1.0.0',
            'status': rule_status,
            'tags': [],
            'created_by': '',
            'created_date': datetime.utcnow().isoformat(),
            'last_modified': datetime.utcnow().isoformat(),
            # Carry MDR UUID so the worker can detect conflicts by UUID
            'mdr_uuid': mdr_uuid,
        },
        'strategy': {
            'mitre_techniques': techniques,
            'detection_approach': '',
            'selected_detection_method': '',
        },
        'capability_abstraction': {
            'mission': {'goal': goal, 'description': technical_context},
            'layers': [
                {
                    'layer_id': 'imported',
                    'layer_name': 'Imported Layer',
                    'capability': 'Detection',
                    'description': '',
                    'nodes': [tvm_node_id, dom_node_id, mdr_node_id],
                }
            ],
        },
        'detection_logic': {
            'detection_rule': detection_rule,
            'rule_format': _infer_rule_format(configurations),
            'data_sources': [],
            'blind_spots': [],
        },
        'operational_context': {
            'goal': goal,
            'technical_context': technical_context,
            'false_positives': [fp.strip() for fp in false_positives.split('\n') if fp.strip()],
            'triage_guidance': triage_guidance,
            'response_playbook': response_playbook,
        },
        'testing': {
            'test_scenario': test_scenario,
            'test_expected_output': test_expected_output,
            'test_environment': '',
            'target_file_path': '',
        },
        'soar_configuration': {
            'alert_trigger': '',
            'default_severity': alert_severity,
            'enrichment_steps': [],
            'containment_steps': [],
            'notification_steps': [],
            'downstream_correlation_requirements': {},
        },
        'graph_structure': {
            'nodes': nodes,
            'edges': edges,
        },
        'audit_trail': {
            'robustness_level': 0,
            'data_source_robustness': '',
            'data_source_maturity': '',
            'notes': '',
            'validation_status': 'Not validated',
        },
    }

    return hex_doc


def _infer_rule_format(configurations: Dict[str, Any]) -> str:
    """Return a human-readable format label for the primary detection config."""
    if 'defender_for_endpoint' in configurations:
        return 'kql'
    if 'microsoft_sentinel' in configurations:
        return 'kql'
    if 'splunk' in configurations:
        return 'spl'
    if 'elastic' in configurations:
        return 'eql'
    if 'wazuh' in configurations:
        return 'wazuh'
    if 'qradar' in configurations:
        return 'aql'
    return 'unknown'


def validate_bundle(
    bundle_files: Dict[str, Optional[str]],
) -> Tuple[bool, List[str]]:
    """Validate the YAML content of a HEF bundle using the existing OpenTIDE validators.

    Returns:
        (is_valid, errors) — ``is_valid`` is ``True`` when there are no errors.
    """
    from playbooks.utils.opentide_validator import (
        validate_bdr_structure,
        validate_dom_structure,
        validate_mdr_structure,
        validate_tvm_structure,
    )

    errors: List[str] = []

    def _parse(text: Optional[str], label: str) -> Optional[Dict]:
        if not text:
            return None
        try:
            return yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            errors.append(f'{label}: YAML parse error: {exc}')
            return None

    mdr_data = _parse(bundle_files.get('mdr'), 'MDR')
    tvm_data = _parse(bundle_files.get('tvm'), 'TVM')
    dom_data = _parse(bundle_files.get('dom'), 'DOM')
    bdr_data = _parse(bundle_files.get('bdr'), 'BDR') if bundle_files.get('bdr') else None

    if errors:
        return False, errors

    if mdr_data is None:
        return False, ['MDR YAML is required but missing or empty']

    for label, fn, data in [
        ('MDR', validate_mdr_structure, mdr_data),
        ('TVM', validate_tvm_structure, tvm_data) if tvm_data else ('TVM', None, None),
        ('DOM', validate_dom_structure, dom_data) if dom_data else ('DOM', None, None),
        ('BDR', validate_bdr_structure, bdr_data) if bdr_data else ('BDR', None, None),
    ]:
        if fn is None or data is None:
            continue
        try:
            is_ok, errs = fn(data)
            if not is_ok:
                errors.extend([f'{label}: {e}' for e in errs])
        except Exception as exc:
            errors.append(f'{label}: validation raised exception: {exc}')

    return len(errors) == 0, errors


def import_per_platform_rules(graph, bundle_files: Dict[str, Any]) -> None:
    """Import per-platform rule files from the bundle into DetectionRule objects.

    Mirrors ``extract_platform_rules_from_opentide`` but reads from already-fetched
    bundle file contents instead of recompiling from a PlaybookGraph.

    Args:
        graph: a saved PlaybookGraph instance.
        bundle_files: dict with optional key ``platform_files``, itself a
            mapping of platform name → list of ``{path, content}`` dicts.
    """
    try:
        from rules.models import DetectionRule
    except ImportError:
        logger.warning('HEF import: rules app not available, skipping platform rule import')
        return

    platform_files = bundle_files.get('platform_files') or {}

    _FORMAT_MAP = {
        'kql': 'KQL',
        'elastic': 'EQL',
        'splunk': 'SPL',
        'sigma': 'SIGMA',
        'wazuh': 'WAZUH',
        'qradar': 'AQL',
    }

    for platform, files in platform_files.items():
        fmt = _FORMAT_MAP.get(platform.lower())
        if not fmt:
            continue
        for file_entry in files if isinstance(files, list) else []:
            content = (
                file_entry.get('content', '')
                if isinstance(file_entry, dict)
                else str(file_entry)
            )
            if not content or not content.strip():
                continue
            try:
                rule, created = DetectionRule.objects.update_or_create(
                    playbook=graph,
                    format=fmt,
                    defaults={
                        'raw_content': content.strip(),
                        'name': f'{graph.title} ({fmt})',
                    },
                )
                action = 'created' if created else 'updated'
                logger.debug(
                    'HEF import: %s DetectionRule %s for graph %s platform %s',
                    action, rule.id, graph.id, platform,
                )
            except Exception as exc:
                logger.warning(
                    'HEF import: failed to upsert DetectionRule for graph %s platform %s: %s',
                    graph.id, platform, exc,
                )
