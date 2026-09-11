from typing import Any, Dict, List, Optional, Tuple
import hashlib
import logging
import uuid

import yaml as pyyaml

from organizations.models import PlatformCredential
from playbooks.utils.opentide_validator import validate_mdr_structure
from rules.deployers import PLATFORM_DEPLOYER_MAP, DeploymentResult
from rules.metadata_injector import inject_metadata
from rules.models import DetectionRule, RuleRepository


logger = logging.getLogger(__name__)


class OpenTideMDRValidationError(ValueError):
    """Raised when MDR payload fails schema validation for HEF publish."""


def _classify_deployment_failure(
    *,
    platform: str,
    message: str,
    errors: list[str],
) -> dict[str, str]:
    """Return a structured failure taxonomy for operator-facing diagnostics."""
    blob = ' '.join([platform or '', message or '', *(errors or [])]).lower()

    if 'invalid_scope' in blob or 'customdetections.readwrite.all' in blob:
        return {
            'failure_type': 'AUTH_SCOPE',
            'probable_cause': 'API app registration is missing required Microsoft Graph application scopes/consent.',
            'operator_hint': 'Grant/consent CustomDetections.ReadWrite.All and re-test token acquisition.',
        }
    if 'unauthorized' in blob or 'http 401' in blob:
        return {
            'failure_type': 'AUTHN',
            'probable_cause': 'Token acquisition failed or bearer token is invalid/expired.',
            'operator_hint': 'Verify tenant/client credentials and secret validity; then test platform connection.',
        }
    if 'forbidden' in blob or 'http 403' in blob:
        return {
            'failure_type': 'AUTHZ',
            'probable_cause': 'Authenticated identity lacks platform permissions for rule write/update.',
            'operator_hint': 'Grant required role/permissions for detection rule management and retry.',
        }
    if (
        'query validation failed' in blob
        or 'invalid query' in blob
        or 'parser' in blob
        or 'kql query' in blob
    ):
        return {
            'failure_type': 'QUERY_VALIDATION',
            'probable_cause': 'Detection query syntax/schema does not match target platform expectations.',
            'operator_hint': 'Validate query tables/columns for the selected platform and re-publish.',
        }
    if 'timeout' in blob or 'request error' in blob or 'connection' in blob:
        return {
            'failure_type': 'NETWORK',
            'probable_cause': 'Transient network/API connectivity issue during deployment.',
            'operator_hint': 'Retry publish; if persistent, verify platform endpoint reachability and proxy/SSL settings.',
        }
    return {
        'failure_type': 'PLATFORM_REJECTED',
        'probable_cause': 'Target platform rejected the deployment payload.',
        'operator_hint': 'Review detailed platform errors and compare payload fields against platform API requirements.',
    }


def build_deployment_failure_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a compact, structured summary from per-platform deployment results."""
    failed = [item for item in (results or []) if not item.get('success')]
    failed_platforms = [str(item.get('platform') or 'Unknown') for item in failed]
    failure_type_counts: Dict[str, int] = {}
    hints: List[str] = []
    for item in failed:
        failure_type = str(item.get('failure_type') or 'UNKNOWN').strip() or 'UNKNOWN'
        failure_type_counts[failure_type] = failure_type_counts.get(failure_type, 0) + 1
        hint = str(item.get('operator_hint') or '').strip()
        if hint and hint not in hints:
            hints.append(hint)

    return {
        'failed_count': len(failed),
        'failed_platforms': failed_platforms,
        'failure_type_counts': failure_type_counts,
        'operator_hints': hints,
    }


def _is_uuid4(value: Any) -> bool:
    if not value:
        return False
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return parsed.version == 4 and parsed.variant == uuid.RFC_4122


def _seeded_uuid4(seed: str) -> str:
    """Generate deterministic UUIDv4 from an arbitrary seed string."""
    digest = hashlib.sha256(seed.encode('utf-8')).digest()
    b = bytearray(digest[:16])
    # Force version nibble to v4
    b[6] = (b[6] & 0x0F) | 0x40
    # Force RFC 4122 variant bits (10xx)
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


def _ensure_mdr_uuid4(mdr_data: Dict[str, Any], fallback_seed: Optional[str] = None) -> None:
    """
    Ensure ``metadata.uuid`` exists and is UUIDv4.

    Legacy payloads may carry UUIDv5 values that fail strict CoreTide MDR schema
    validation. To keep publishing resilient, we normalize invalid/missing values
    to a deterministic UUIDv4 derived from stable MDR identifiers.
    """
    if not isinstance(mdr_data, dict):
        return

    metadata = mdr_data.get('metadata')
    if not isinstance(metadata, dict):
        metadata = {}
        mdr_data['metadata'] = metadata

    current = metadata.get('uuid')
    if _is_uuid4(current):
        return

    seed_parts = [
        str(current or '').strip(),
        str(mdr_data.get('name') or '').strip(),
        str(metadata.get('title') or '').strip(),
        str(metadata.get('schema') or 'mdr::2.1').strip(),
        str(fallback_seed or '').strip(),
    ]
    normalized_seed = '|'.join(part for part in seed_parts if part)
    if not normalized_seed:
        normalized_seed = 'hefaistos|mdr'

    metadata['uuid'] = _seeded_uuid4(normalized_seed)
    logger.warning(
        'Normalized MDR metadata.uuid to UUIDv4 for HEF publish (previous=%r, normalized=%s)',
        current,
        metadata['uuid'],
    )


def _to_upper_severity(value: Optional[str]) -> str:
    if not value:
        return 'MEDIUM'
    normalized = str(value).strip().upper()
    if normalized in ('INFORMATIONAL', 'INFO'):
        return 'LOW'
    if normalized in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'):
        return normalized
    # MDR values are often title-case (e.g. High, Medium)
    title_to_upper = {
        'LOW': 'LOW',
        'MEDIUM': 'MEDIUM',
        'HIGH': 'HIGH',
        'CRITICAL': 'CRITICAL',
    }
    return title_to_upper.get(normalized, 'MEDIUM')


def _extract_mitre_technique_from_mdr(mdr_data: Dict[str, Any]) -> str:
    """Best-effort extraction of a MITRE technique id from an MDR payload.

    Tried in order so that non-Defender-only MDRs still surface a technique:

    1. ``configurations.defender_for_endpoint.alert.techniques[0]``
    2. ``metadata.mitre.technique_id`` (set by ``compile_mdr_yaml``)
    3. Any other ``configurations.<platform>.alert.techniques[0]`` value
    4. ``"T0000"`` as a last-resort placeholder.
    """
    if not isinstance(mdr_data, dict):
        return 'T0000'

    # 1) Defender alert techniques (preferred).
    try:
        techniques = (
            mdr_data.get('configurations', {})
            .get('defender_for_endpoint', {})
            .get('alert', {})
            .get('techniques', [])
        )
        if isinstance(techniques, list) and techniques:
            first = techniques[0]
            if isinstance(first, str) and first.strip():
                return first.strip()
    except Exception:
        pass

    # 2) metadata.mitre.technique_id from compile_mdr_yaml().
    metadata = mdr_data.get('metadata') if isinstance(mdr_data.get('metadata'), dict) else None
    if metadata:
        mitre = metadata.get('mitre') if isinstance(metadata.get('mitre'), dict) else None
        if mitre:
            technique_id = mitre.get('technique_id')
            if isinstance(technique_id, str) and technique_id.strip():
                return technique_id.strip()

    # 3) Any other platform that exposes alert.techniques[0].
    configurations = mdr_data.get('configurations') if isinstance(mdr_data.get('configurations'), dict) else {}
    for platform_cfg in configurations.values():
        if not isinstance(platform_cfg, dict):
            continue
        alert = platform_cfg.get('alert') if isinstance(platform_cfg.get('alert'), dict) else None
        if not alert:
            continue
        techniques = alert.get('techniques')
        if isinstance(techniques, list) and techniques:
            first = techniques[0]
            if isinstance(first, str) and first.strip():
                return first.strip()

    return 'T0000'


def mdr_to_deployer_payload(mdr_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform MDR object format into the metadata+platforms shape expected by deployers.
    """
    metadata = mdr_data.get('metadata', {}) if isinstance(mdr_data.get('metadata'), dict) else {}
    configurations = mdr_data.get('configurations', {}) if isinstance(mdr_data.get('configurations'), dict) else {}

    defender_cfg = configurations.get('defender_for_endpoint', {}) if isinstance(configurations.get('defender_for_endpoint'), dict) else {}
    sentinel_cfg = configurations.get('microsoft_sentinel', {}) if isinstance(configurations.get('microsoft_sentinel'), dict) else {}
    alert_cfg = defender_cfg.get('alert', {}) if isinstance(defender_cfg.get('alert'), dict) else {}

    payload_metadata: Dict[str, Any] = {
        'title': alert_cfg.get('title') or mdr_data.get('name') or 'OpenTIDE Rule',
        'description': mdr_data.get('description') or alert_cfg.get('description') or '',
        'author': metadata.get('author') or 'unknown',
        'severity': _to_upper_severity(
            alert_cfg.get('severity')
            or mdr_data.get('response', {}).get('alert_severity')
            if isinstance(mdr_data.get('response'), dict)
            else None
        ),
        'mitre_technique': _extract_mitre_technique_from_mdr(mdr_data),
        'uuid': metadata.get('uuid'),
    }

    platforms: Dict[str, Any] = {}

    query = defender_cfg.get('query') or sentinel_cfg.get('query')
    if isinstance(query, str) and query.strip():
        kql_entry: Dict[str, Any] = {'query': query.strip()}
        # Propagate the MDR-level scheduling period (e.g. "1H") so the
        # Graph deployer can use the correct enum value instead of the default.
        scheduling = defender_cfg.get('scheduling')
        if isinstance(scheduling, str) and scheduling.strip():
            kql_entry['schedule'] = {'period': scheduling.strip()}
        platforms['kql'] = kql_entry

    spl_cfg = configurations.get('splunk', {}) if isinstance(configurations.get('splunk'), dict) else {}
    spl_query = spl_cfg.get('query')
    if isinstance(spl_query, str) and spl_query.strip():
        platforms['spl'] = {
            'query': spl_query.strip(),
        }

    wazuh_cfg = configurations.get('wazuh', {}) if isinstance(configurations.get('wazuh'), dict) else {}
    wazuh_rule = wazuh_cfg.get('rule')
    if isinstance(wazuh_rule, str) and wazuh_rule.strip():
        platforms['wazuh'] = {
            'rule': wazuh_rule.strip(),
        }

    qradar_cfg = configurations.get('qradar', {}) if isinstance(configurations.get('qradar'), dict) else {}
    qradar_query = qradar_cfg.get('query')
    if isinstance(qradar_query, str) and qradar_query.strip():
        platforms['qradar'] = {
            'query': qradar_query.strip(),
        }

    # MDR may also carry an ``elastic`` block (emitted by ``compile_mdr_yaml``
    # when the workbench has an ELASTIC/EQL detection).  No deployer is wired
    # for ``elastic`` in ``rules.deployers.PLATFORM_DEPLOYER_MAP`` yet, so this
    # entry is currently informational – it survives the MDR→deployer payload
    # transform so a future ElasticDeployer can be added without re-shaping
    # the contract.
    elastic_cfg = configurations.get('elastic', {}) if isinstance(configurations.get('elastic'), dict) else {}
    elastic_query = elastic_cfg.get('query')
    if isinstance(elastic_query, str) and elastic_query.strip():
        platforms['elastic'] = {
            'query': elastic_query.strip(),
        }

    payload: Dict[str, Any] = {
        'metadata': payload_metadata,
        'platforms': platforms,
    }
    if defender_cfg or sentinel_cfg:
        payload['configurations'] = {}
        if defender_cfg:
            # Preserve Defender-native blocks (alert, impacted_entities, scope,
            # scheduling, etc.) so Graph deployment can consume MDR semantics.
            payload['configurations']['defender_for_endpoint'] = dict(defender_cfg)
        if sentinel_cfg:
            # Preserve Sentinel-native scheduling/alert settings so the Sentinel
            # deployer can apply them instead of generic defaults.
            payload['configurations']['microsoft_sentinel'] = dict(sentinel_cfg)
    return payload


def upsert_opentide_rule_for_graph(graph, user, raw_yaml: str, repository=None) -> DetectionRule:
    try:
        rule_data = pyyaml.safe_load(raw_yaml) or {}
    except Exception as exc:
        raise ValueError(f'Invalid OpenTIDE YAML: {exc}') from exc

    _ensure_mdr_uuid4(rule_data, fallback_seed=str(getattr(graph, 'id', '')))
    mdr_valid, mdr_errors = validate_mdr_structure(rule_data)
    if not mdr_valid:
        raise OpenTideMDRValidationError('; '.join(mdr_errors))

    deployable_payload = mdr_to_deployer_payload(rule_data)
    payload_metadata = deployable_payload.get('metadata', {})

    metadata = rule_data.get('metadata', {}) if isinstance(rule_data, dict) else {}
    if repository is None:
        repository = RuleRepository.objects.filter(
            organization=user.organization,
            name='Rule Repo',
        ).first()
        if repository is None:
            repository = RuleRepository.objects.create(
                organization=user.organization,
                name='Rule Repo',
                git_url=None,
            )

    defaults = {
        'title': payload_metadata.get('title') or f"{graph.title}-opentide",
        'description': payload_metadata.get('description') or rule_data.get('description', ''),
        'author': metadata.get('author', user.username or 'unknown'),
        'status': (
            metadata.get('status', 'experimental')
            if isinstance(metadata, dict)
            else 'experimental'
        ),
        'raw_content': raw_yaml,
        'organization': user.organization,
        'repository': repository,
        'format': 'OPENTIDE',
    }
    rule, created = DetectionRule.objects.update_or_create(
        organization=user.organization,
        playbook=graph,
        format='OPENTIDE',
        defaults=defaults,
    )

    if created:
        rule.author = user.username or 'unknown'
        rule.save(update_fields=['author'])

    raw_yaml_with_metadata = inject_metadata(
        rule_content=raw_yaml,
        rule_format='OPENTIDE',
        author=graph.author.username if graph.author else 'Unknown',
        rule_name=graph.title,
        severity=graph.default_severity if graph.default_severity else 'NA',
        status=graph.status if graph.status else 'NA',
        mitre_technique=graph.mitre_technique.technique_id if graph.mitre_technique else 'NA',
        rule_id=str(rule.sigma_id),
    )
    rule.raw_content = raw_yaml_with_metadata
    rule.save(update_fields=['raw_content'])
    return rule


def deploy_opentide_rule_to_platforms(rule, organization, platforms: List[str]) -> Tuple[List[Dict[str, Any]], bool, str]:
    if rule.format != 'OPENTIDE':
        raise ValueError('Only OPENTIDE-format rules can be deployed')

    try:
        rule_data = pyyaml.safe_load(rule.raw_content) or {}
    except Exception as exc:
        raise ValueError(f'Failed to parse rule YAML: {exc}') from exc

    deploy_payload = rule_data
    # MDR payloads include top-level `configurations` and may also include
    # a list-valued `platforms` field (target OS list), which is not the
    # deployer contract (`platforms` must be a dict keyed by format).
    # Always convert MDR-shaped payloads before deployment.
    if isinstance(rule_data, dict) and 'configurations' in rule_data:
        _ensure_mdr_uuid4(rule_data, fallback_seed=str(getattr(rule, 'playbook_id', '') or ''))
        mdr_valid, mdr_errors = validate_mdr_structure(rule_data)
        if not mdr_valid:
            raise OpenTideMDRValidationError('; '.join(mdr_errors))
        deploy_payload = mdr_to_deployer_payload(rule_data)

    valid_platforms = set(PLATFORM_DEPLOYER_MAP.keys())
    requested = [p.lower() for p in (platforms or [])]
    unknown = [p for p in requested if p not in valid_platforms]
    if unknown:
        raise ValueError(f"Unknown platform(s): {', '.join(unknown)}")

    cred_map = PlatformCredential.preferred_credentials_map(
        organization=organization,
        platforms=requested,
    )

    deployers: list[tuple[str, object]] = []
    skipped_results: list[DeploymentResult] = []
    for platform_key in requested:
        if platform_key not in cred_map:
            skipped_results.append(
                DeploymentResult(
                    platform=PLATFORM_DEPLOYER_MAP[platform_key].PLATFORM_NAME,
                    success=False,
                    message=f'No credentials configured for {platform_key}. Please add credentials via platform settings.',
                )
            )
            continue
        deployer_cls = PLATFORM_DEPLOYER_MAP[platform_key]
        deployers.append((platform_key, deployer_cls(cred_map[platform_key])))

    outcomes: list[DeploymentResult] = list(skipped_results)

    def _run_deployer(item):
        _, deployer = item
        return deployer.run(deploy_payload)

    if deployers:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(deployers)) as pool:
            for result in pool.map(_run_deployer, deployers):
                outcomes.append(result)

    results = [
        (
            {
                'platform': r.platform,
                'success': r.success,
                'rule_id': r.rule_id,
                'message': r.message,
                'errors': r.errors or [],
            }
            | (
                {}
                if r.success
                else _classify_deployment_failure(
                    platform=r.platform,
                    message=r.message,
                    errors=r.errors or [],
                )
            )
        )
        for r in outcomes
    ]
    overall_success = all(r['success'] for r in results) if results else True
    message = f"Deployed to {sum(1 for r in results if r['success'])}/{len(results)} platform(s) successfully."
    return results, overall_success, message
