"""
Microsoft Defender for Endpoint deployment engine.

Authenticates via OAuth 2.0 client_credentials flow against the Microsoft
identity platform and deploys custom detection rules (KQL-based) to the
Defender for Endpoint custom detections API.

Required credentials:
    tenant_id      – Azure AD tenant ID
    client_id      – App registration client (application) ID
    client_secret  – App registration client secret
"""

import logging
import re
import requests

from .base import PlatformDeployer, DeploymentResult, parse_http_error

logger = logging.getLogger(__name__)

_TOKEN_URL = 'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'

# Legacy WindowsDefenderATP / Microsoft 365 Defender REST scope.
_SCOPE = 'https://api.securitycenter.microsoft.com/.default'
# Microsoft Graph scope for the modern Security custom detection rules API.
_GRAPH_SCOPE = 'https://graph.microsoft.com/.default'

# Modern Microsoft Graph Security API endpoints (preferred).
# Microsoft retired the WindowsDefenderATP custom detection rules surface
# (returns HTTP 405 on api.securitycenter.microsoft.com / api.security.microsoft.com)
# and migrated custom detection rules to Microsoft Graph.
# Only the /beta/ segment exists today; /v1.0/ returns
# "Resource not found for the segment 'rules'" (May 2026).
_GRAPH_DETECTION_ENDPOINTS = [
    'https://graph.microsoft.com/beta/security/rules/detectionRules',
]

# Microsoft Graph custom detection rules accept a fixed enum for the
# schedule period (NOT ISO 8601). Allowed values: 0, 1H, 3H, 12H, 24H.
_GRAPH_ALLOWED_PERIODS = {'0', '1H', '3H', '12H', '24H'}
_GRAPH_DEFAULT_PERIOD = '1H'


def _to_graph_rule_id(uuid_str: str) -> str:
    """Convert a UUID string to a Graph-compliant rule identifier.

    Microsoft Graph custom detection rules require the rule ID to:
    - consist of letters, numbers, dashes, and underscores only
    - begin with a letter
    - be at most 100 characters long

    UUIDs are already letters/digits/dashes but can start with a digit.
    We prefix with 'r' in that case so e.g. ``3b4d99a1-...`` becomes
    ``r3b4d99a1-...`` (still unambiguous, still under 100 chars).
    """
    s = uuid_str.strip()
    if s and not s[0].isalpha():
        s = 'r' + s
    return s[:100]


def _normalize_graph_period(value: str | None) -> str:
    """Coerce arbitrary period strings to the Graph-allowed enum.

    Accepts ISO 8601 (PT1H, PT3H, PT12H, PT24H, PT0S, P1D) and the bare
    enum values themselves. Falls back to the default when nothing matches.
    """
    if not value:
        return _GRAPH_DEFAULT_PERIOD
    raw = str(value).strip().upper()
    if raw in _GRAPH_ALLOWED_PERIODS:
        return raw
    # Strip ISO 8601 'PT' prefix and trailing 'S'/'M' for minutes/seconds.
    candidate = raw
    if candidate.startswith('PT'):
        candidate = candidate[2:]
    if candidate in _GRAPH_ALLOWED_PERIODS:
        return candidate
    # Common ISO synonyms.
    iso_map = {
        'PT0S': '0',
        '0S': '0',
        'P1D': '24H',
        '1D': '24H',
    }
    if raw in iso_map:
        return iso_map[raw]
    return _GRAPH_DEFAULT_PERIOD

# Legacy host endpoints kept as best-effort fallback for older tenants.
_DETECTION_RULES_ENDPOINTS = [
    'https://api.securitycenter.microsoft.com/api/customDetectionRules',
    'https://api.securitycenter.microsoft.com/api/detectionRules',
    'https://api.security.microsoft.com/api/customDetectionRules',
    'https://api.security.microsoft.com/api/detectionRules',
]

# Microsoft Graph severity enumeration (lowercase strings).
_GRAPH_SEVERITY_MAP = {
    'INFORMATIONAL': 'informational',
    'INFO': 'informational',
    'LOW': 'low',
    'MEDIUM': 'medium',
    'HIGH': 'high',
}

_RULE_NAME_RE = re.compile(r'^\s*//\s*Rule name:\s*(.+?)\s*$', re.IGNORECASE | re.MULTILINE)
_TAGS_RE = re.compile(r'^\s*//\s*tags:\s*(.+?)\s*$', re.IGNORECASE | re.MULTILINE)

# ---------------------------------------------------------------------------
# Defender Advanced Hunting schema validation
# ---------------------------------------------------------------------------

# Tables that exist in Defender Advanced Hunting (Microsoft 365 Defender).
# This list is used to detect queries that reference unsupported tables
# (e.g. Azure Monitor / Log Analytics tables) before sending to the API.
_DEFENDER_AH_TABLES: frozenset[str] = frozenset({
    # Endpoint / device tables
    'DeviceProcessEvents', 'DeviceNetworkEvents', 'DeviceFileEvents',
    'DeviceRegistryEvents', 'DeviceLogonEvents', 'DeviceImageLoadEvents',
    'DeviceEvents', 'DeviceFileCertificateInfo', 'DeviceNetworkInfo',
    'DeviceInfo', 'DeviceTvmSoftwareInventory', 'DeviceTvmSoftwareVulnerabilities',
    'DeviceTvmSoftwareVulnerabilitiesKB', 'DeviceTvmSecureConfigurationAssessment',
    'DeviceTvmSecureConfigurationAssessmentKB',
    # Alert tables
    'AlertInfo', 'AlertEvidence',
    # Email / O365 tables
    'EmailEvents', 'EmailAttachmentInfo', 'EmailUrlInfo', 'EmailPostDeliveryEvents',
    'UrlClickEvents',
    # Cloud app tables
    'CloudAppEvents',
    # Identity tables
    'IdentityLogonEvents', 'IdentityQueryEvents', 'IdentityDirectoryEvents',
    'IdentityInfo',
    # App & behaviour tables
    'AppFileEvents', 'BehaviorEntities', 'BehaviorInfo',
    # AAD sign-in (beta)
    'AADSpnSignInEventsBeta', 'AADSignInEventsBeta',
})

# Known Azure Monitor / Log Analytics tables that are NOT in Defender AH.
# Used to surface a more specific "you used the wrong table" error.
_NON_DEFENDER_TABLES: frozenset[str] = frozenset({
    'Heartbeat', 'Syslog', 'SecurityEvent', 'CommonSecurityLog',
    'AzureActivity', 'AzureDiagnostics', 'AzureMetrics',
    'Event', 'Perf', 'Update', 'UpdateSummary',
    'W3CIISLog', 'WindowsFirewall', 'WireData',
    'InsightsMetrics', 'ContainerLog', 'KubeEvents',
    'Operation', 'Usage',
})

# Simple word-boundary regex to find bare table names in KQL.
_TABLE_NAME_RE = re.compile(r'\b([A-Z][A-Za-z0-9]+)\b')


def _query_references_defender_table(query: str) -> bool:
    """Return True if any Defender Advanced Hunting table name appears in the query."""
    tokens = set(_TABLE_NAME_RE.findall(query))
    return bool(tokens & _DEFENDER_AH_TABLES)


def _detect_non_defender_tables(query: str) -> list[str]:
    """Return any known non-Defender table names found in the query."""
    tokens = set(_TABLE_NAME_RE.findall(query))
    return sorted(tokens & _NON_DEFENDER_TABLES)


# ---------------------------------------------------------------------------
# Impacted-asset detection
# ---------------------------------------------------------------------------
# Defender Graph API validates that the query output contains the column that
# matches the declared impacted-asset identifier (e.g. impactedDeviceAsset +
# deviceId requires a projected 'DeviceId' column).  Sending the wrong
# identifier for the query schema produces an opaque HTTP 500.  We therefore
# scan the query for known identifier column names and pick the best match.

_ASSET_COLUMN_PRIORITY: list[tuple[str, str, str]] = [
    # (column_name_to_detect, odata_type_suffix, identifier_value)
    ('DeviceId',                    'impactedDeviceAsset',           'deviceId'),
    ('DeviceName',                  'impactedDeviceAsset',           'deviceName'),
    ('DeviceDnsName',               'impactedDeviceAsset',           'deviceDnsName'),
    ('AccountObjectId',             'impactedUserAsset',             'accountObjectId'),
    ('AccountUpn',                  'impactedUserAsset',             'accountUpn'),
    ('InitiatingProcessAccountUpn', 'impactedUserAsset',             'accountUpn'),
    ('AccountSid',                  'impactedUserAsset',             'accountSid'),
    ('AccountName',                 'impactedUserAsset',             'accountName'),
    ('AccountDisplayName',          'impactedUserAsset',             'accountDisplayName'),
    ('IPAddress',                   'impactedIpAddressAsset',        'ipAddress'),
    ('RemoteIP',                    'impactedIpAddressAsset',        'ipAddress'),
    ('Url',                         'impactedUrlAsset',              'url'),
    ('AppId',                       'impactedCloudApplicationAsset', 'appId'),
]

_DEFAULT_IMPACTED_ASSET: dict = {
    '@odata.type': '#microsoft.graph.security.impactedDeviceAsset',
    'identifier': 'deviceId',
}


def _pick_impacted_asset(query: str) -> dict:
    """Return the best-matching impactedAsset dict based on columns referenced in the query.

    Defender's Graph API requires the query result to contain the column that
    corresponds to the declared impacted-asset identifier.  We scan the query
    tokens (including alias assignments like ``DeviceId = foo``) and return the
    first match from the priority list.  Falls back to impactedDeviceAsset/deviceId.
    """
    tokens = set(re.findall(r'\b([A-Za-z][A-Za-z0-9_]*)\b', query))
    for col, type_suffix, identifier in _ASSET_COLUMN_PRIORITY:
        if col in tokens:
            return {
                '@odata.type': f'#microsoft.graph.security.{type_suffix}',
                'identifier': identifier,
            }
    return dict(_DEFAULT_IMPACTED_ASSET)


def _pick_impacted_asset_from_config(query: str, defender_conf: dict | None) -> dict:
    """Use ``impacted_entities`` mapping when possible, else infer from query.

    ``defender_for_endpoint.impacted_entities`` typically declares columns like
    ``device: DeviceName``. We map those declared columns onto Graph's
    impactedAsset identifiers when a known column is provided.
    """
    if isinstance(defender_conf, dict):
        impacted_entities = defender_conf.get('impacted_entities')
        if isinstance(impacted_entities, dict):
            for entity_type in ('device', 'user', 'mailbox'):
                raw_col = impacted_entities.get(entity_type)
                col = str(raw_col or '').strip()
                if not col:
                    continue
                for known_col, type_suffix, identifier in _ASSET_COLUMN_PRIORITY:
                    if known_col.lower() == col.lower():
                        return {
                            '@odata.type': f'#microsoft.graph.security.{type_suffix}',
                            'identifier': identifier,
                        }
    return _pick_impacted_asset(query)


def _extract_query_metadata(query: str) -> tuple[str | None, list[str]]:
    rule_name_match = _RULE_NAME_RE.search(query or '')
    tags_match = _TAGS_RE.search(query or '')

    rule_name = rule_name_match.group(1).strip() if rule_name_match else None
    tags: list[str] = []
    if tags_match:
        tags = [tag.strip() for tag in tags_match.group(1).split(',') if tag.strip()]

    return rule_name, tags


class DefenderDeployer(PlatformDeployer):
    """Deploys KQL detection rules to Microsoft Defender for Endpoint."""

    PLATFORM_NAME = 'Microsoft Defender'

    # ------------------------------------------------------------------
    # Credential validation
    # ------------------------------------------------------------------

    def validate_credentials(self) -> tuple[bool, str]:
        required = ('tenant_id', 'client_id', 'client_secret')
        missing = [k for k in required if not self.credentials.get(k)]
        if missing:
            return False, f"Missing required fields: {', '.join(missing)}"
        return True, ''

    def _legacy_fallback_enabled(self) -> bool:
        """Return True if the deprecated WindowsDefenderATP endpoints should be tried.

        The legacy ``api.securitycenter.microsoft.com`` / ``api.security.microsoft.com``
        custom detection rules surface has been retired by Microsoft and now
        consistently returns HTTP 405. Falling back to it only obscures the real
        error from Microsoft Graph, so it is disabled by default and must be
        explicitly opted into via the ``allow_legacy_fallback`` credential flag.
        """
        return bool(self.credentials.get('allow_legacy_fallback'))

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        tenant_id = self.credentials['tenant_id']
        token_url = _TOKEN_URL.format(tenant_id=tenant_id)
        common = {
            'grant_type': 'client_credentials',
            'client_id': self.credentials['client_id'],
            'client_secret': self.credentials['client_secret'],
        }

        # Legacy token (best effort — some tenants no longer grant this scope).
        self._token = None
        try:
            resp = requests.post(token_url, data={**common, 'scope': _SCOPE}, timeout=30)
            if resp.ok:
                self._token = resp.json().get('access_token')
            else:
                logger.warning(
                    '[%s] Could not acquire legacy securitycenter token (HTTP %s); '
                    'will rely on Microsoft Graph token instead.',
                    self.PLATFORM_NAME,
                    resp.status_code,
                )
        except requests.RequestException as exc:
            logger.warning('[%s] Legacy token request failed: %s', self.PLATFORM_NAME, exc)

        # Microsoft Graph token (primary, required for modern API).
        self._graph_token = None
        self._graph_token_error: str | None = None
        try:
            resp = requests.post(token_url, data={**common, 'scope': _GRAPH_SCOPE}, timeout=30)
            if resp.ok:
                self._graph_token = resp.json().get('access_token')
            else:
                excerpt = (resp.text or '').strip().replace('\n', ' ')[:300]
                self._graph_token_error = (
                    f'HTTP {resp.status_code} from Microsoft Graph token endpoint: '
                    f'{excerpt or "<empty>"}'
                )
                logger.error('[%s] Microsoft Graph token request failed: %s', self.PLATFORM_NAME, self._graph_token_error)
        except requests.RequestException as exc:
            self._graph_token_error = f'Microsoft Graph token request error: {exc}'
            logger.error('[%s] %s', self.PLATFORM_NAME, self._graph_token_error)

        # Without a Graph token we cannot deploy unless the operator has
        # explicitly opted into the retired legacy fallback.
        if not self._graph_token and not self._legacy_fallback_enabled():
            return False
        if not (self._token or self._graph_token):
            return False

        logger.info(
            '[%s] Authenticated successfully (legacy=%s graph=%s).',
            self.PLATFORM_NAME,
            bool(self._token),
            bool(self._graph_token),
        )
        return True

    # ------------------------------------------------------------------
    # Rule deployment
    # ------------------------------------------------------------------

    def deploy_rule(self, rule_data: dict) -> DeploymentResult:
        platforms = rule_data.get('platforms', {})
        if not isinstance(platforms, dict):
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message=(
                    'Invalid OpenTide payload: platforms must be an object '
                    f'but received {type(platforms).__name__}.'
                ),
            )
        kql_block = platforms.get('kql', {})
        query = kql_block.get('query', '') if isinstance(kql_block, dict) else ''

        if not query:
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message='No KQL query found in OpenTide rule for Defender deployment.',
            )

        is_valid, errors = self.validate_query(query, rule_data)
        if not is_valid:
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message='KQL query validation failed.',
                errors=errors,
            )
        if errors:
            for warning in errors:
                logger.info('[%s] KQL pre-flight warning: %s', self.PLATFORM_NAME, warning)

        metadata = rule_data.get('metadata', {})
        configurations = rule_data.get('configurations', {}) if isinstance(rule_data, dict) else {}
        defender_conf = (
            configurations.get('defender_for_endpoint', {})
            if isinstance(configurations, dict)
            else {}
        )
        defender_alert = (
            defender_conf.get('alert', {})
            if isinstance(defender_conf, dict) and isinstance(defender_conf.get('alert'), dict)
            else {}
        )
        query_rule_name, query_tags = _extract_query_metadata(query)

        display_name = (
            query_rule_name
            or defender_alert.get('title')
            or metadata.get('title')
            or 'OpenTide Rule'
        )
        description = metadata.get('description', '')
        if isinstance(defender_alert.get('description'), str) and defender_alert.get('description').strip():
            description = defender_alert.get('description').strip()
        if query_tags:
            tag_line = f"Tags: {', '.join(query_tags)}"
            description = f"{description}\n\n{tag_line}".strip() if description else tag_line

        rule_uuid = str(metadata.get('uuid', '')).strip()
        raw_severity = str(defender_alert.get('severity') or metadata.get('severity', 'MEDIUM')).upper()
        legacy_severity = raw_severity.capitalize()
        graph_severity = _GRAPH_SEVERITY_MAP.get(raw_severity, 'medium')
        raw_enabled = defender_alert.get('enabled', True)
        if isinstance(raw_enabled, bool):
            alert_enabled = raw_enabled
        elif isinstance(raw_enabled, str):
            alert_enabled = raw_enabled.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            alert_enabled = bool(raw_enabled)

        # Schedule period — Graph requires the enum 0|1H|3H|12H|24H.
        # Accept either ISO 8601 (PT1H) or bare enum from MDR; coerce safely.
        schedule_block = kql_block.get('schedule') if isinstance(kql_block, dict) else None
        raw_period = schedule_block.get('period') if isinstance(schedule_block, dict) else None
        schedule_period = _normalize_graph_period(raw_period)

        # ------------------------------------------------------------------
        # Legacy WindowsDefenderATP payload (api.securitycenter.microsoft.com).
        # ------------------------------------------------------------------
        legacy_payload = {
            'displayName': display_name,
            'description': description,
            'severity': legacy_severity,
            'isEnabled': alert_enabled,
            'queryCondition': {'queryText': query},
            'triggerThreshold': 0,
            'triggerOperator': 'GreaterThan',
            'detectionAction': {'alertTitle': display_name},
        }

        # ------------------------------------------------------------------
        # Microsoft Graph Security API payload
        # (graph.microsoft.com/.../security/rules/detectionRules).
        # Only include optional fields when they carry a value; sending
        # null / empty strings causes generic "Bad request" from the API.
        # ------------------------------------------------------------------
        # Microsoft Graph requires @odata.type annotations on nested objects
        # so the beta endpoint can deserialize the body correctly.
        # Omitting them produces an opaque HTTP 500 "InternalServerError".
        # ------------------------------------------------------------------
        graph_alert_template: dict = {
            '@odata.type': '#microsoft.graph.security.alertTemplate',
            'title': display_name,
            'severity': graph_severity,
            # 'SuspiciousActivity' is the generic catch-all in Defender's
            # alertCategory enum and is always accepted by the Graph API.
            'category': 'SuspiciousActivity',
            # Graph requires at least one impacted asset entry.
            # Default to deviceId (standard for KQL/Defender for Endpoint rules).
            'impactedAssets': [_pick_impacted_asset_from_config(query, defender_conf)],
        }
        if description:
            graph_alert_template['description'] = description

        graph_detection_action: dict = {
            '@odata.type': '#microsoft.graph.security.detectionAction',
            'alertTemplate': graph_alert_template,
        }

        graph_payload: dict = {
            '@odata.type': '#microsoft.graph.security.detectionRule',
            'displayName': display_name,
            'isEnabled': alert_enabled,
            'queryCondition': {
                '@odata.type': '#microsoft.graph.security.queryCondition',
                'queryText': query,
            },
            'schedule': {
                '@odata.type': '#microsoft.graph.security.ruleSchedule',
                'period': schedule_period,
            },
            'detectionAction': graph_detection_action,
        }
        graph_detector_id = self.credentials.get('graph_detector_id') if hasattr(self, 'credentials') else None
        if graph_detector_id:
            graph_payload['detectorId'] = graph_detector_id

        # Graph-safe rule identifier (must start with a letter; max 100 chars).
        graph_rule_id = _to_graph_rule_id(rule_uuid) if rule_uuid else ''

        import json as _json
        graph_payload_json = _json.dumps(graph_payload, indent=2, default=str)
        logger.info(
            '[%s] Creating Defender custom detection rule displayName=%r severity=%r query_length=%d tags=%s\nGraph payload:\n%s',
            self.PLATFORM_NAME,
            display_name,
            legacy_severity,
            len(query),
            query_tags,
            graph_payload_json,
        )

        graph_token = getattr(self, '_graph_token', None)
        legacy_token = getattr(self, '_token', None)
        graph_token_error = getattr(self, '_graph_token_error', None)
        legacy_fallback_enabled = self._legacy_fallback_enabled()

        # ------------------------------------------------------------------
        # Graph API attempts (preferred) — with upsert-by-displayName recovery.
        # Microsoft Graph returns HTTP 500 when a rule with the same displayName
        # already exists (instead of 409 Conflict).  After any 5xx POST we
        # check the rule list for a matching displayName and PATCH it instead.
        # ------------------------------------------------------------------
        graph_error_result: 'DeploymentResult | None' = None
        if graph_token:
            for graph_base in _GRAPH_DETECTION_ENDPOINTS:
                result = self._graph_upsert(
                    graph_base, graph_payload, graph_rule_id, display_name,
                    graph_token,
                )
                if result is not None:
                    if result.success:
                        return result
                    # Remember the most recent definitive Graph failure so we
                    # can surface it instead of a misleading legacy-405 error.
                    graph_error_result = result

        # ------------------------------------------------------------------
        # Legacy WindowsDefenderATP fallback — opt-in only.
        # The retired ``api.securitycenter.microsoft.com`` and
        # ``api.security.microsoft.com`` endpoints now consistently return
        # HTTP 405; trying them only obscures the real Graph error. Operators
        # may still enable them by setting the credential flag
        # ``allow_legacy_fallback`` to ``true``.
        # ------------------------------------------------------------------
        if not legacy_fallback_enabled:
            if graph_error_result is not None:
                return graph_error_result
            if not graph_token:
                hint = (
                    "Microsoft Graph token was not acquired; cannot deploy. "
                    "Ensure the Azure AD app registration has the Microsoft Graph "
                    "application permission 'CustomDetections.ReadWrite.All' (with "
                    "admin consent) and that the tenant is licensed for Microsoft "
                    "Defender XDR. To temporarily try the deprecated WindowsDefenderATP "
                    "endpoints, set the credential flag 'allow_legacy_fallback' to true."
                )
                if graph_token_error:
                    hint = f'{hint} Token error: {graph_token_error}'
                return DeploymentResult(
                    platform=self.PLATFORM_NAME,
                    success=False,
                    message=hint,
                )
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message='Failed to create Defender custom detection rule via Microsoft Graph (no further detail).',
            )

        # ------------------------------------------------------------------
        # Legacy WindowsDefenderATP fallback (POST then PUT) — opt-in.
        # ------------------------------------------------------------------
        endpoint_errors: list[str] = []
        if legacy_token:
            legacy_attempts: list[tuple[str, str]] = [
                ('POST', ep) for ep in _DETECTION_RULES_ENDPOINTS
            ]
            if rule_uuid:
                legacy_attempts += [
                    ('PUT', f"{ep.rstrip('/')}/{rule_uuid}") for ep in _DETECTION_RULES_ENDPOINTS
                ]
            for method, endpoint in legacy_attempts:
                headers = {
                    'Authorization': f'Bearer {legacy_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                }
                try:
                    logger.info('[%s] Trying legacy endpoint: %s %s', self.PLATFORM_NAME, method, endpoint)
                    resp = requests.request(method, endpoint, json=legacy_payload, headers=headers, timeout=30)
                    if 200 <= resp.status_code < 300:
                        result_data = resp.json() if resp.content else {}
                        rule_id = str(result_data.get('id', '')) or rule_uuid
                        logger.info('[%s] Legacy rule deployed: %s', self.PLATFORM_NAME, rule_id)
                        return DeploymentResult(
                            platform=self.PLATFORM_NAME, success=True, rule_id=rule_id,
                            message=f'Custom detection rule deployed successfully (ID: {rule_id})',
                        )
                    summary, details = parse_http_error(resp, platform=self.PLATFORM_NAME)
                    endpoint_errors.append(f'{method} {endpoint}: {summary}')
                    endpoint_errors.extend(details)
                except requests.RequestException as exc:
                    endpoint_errors.append(f'Request error for {method} {endpoint}: {exc}')

        if not graph_token and not legacy_token:
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message='No Defender access tokens were acquired; cannot deploy rule.',
            )

        # Prefer the Graph error if we have one — the legacy 405 is just noise.
        if graph_error_result is not None:
            return graph_error_result

        last_error = '; '.join(endpoint_errors) if endpoint_errors else 'No Graph token available and no legacy endpoints succeeded.'
        return DeploymentResult(
            platform=self.PLATFORM_NAME,
            success=False,
            message='Failed to create Defender custom detection rule. See errors for details.',
            errors=endpoint_errors[:20] if endpoint_errors else [last_error],
        )

    def _graph_upsert(
        self,
        base_endpoint: str,
        payload: dict,
        graph_rule_id: str,
        display_name: str,
        token: str,
    ) -> 'DeploymentResult | None':
        """
        Try to create (POST) then, on 5xx, recover by finding and updating
        (PATCH) an existing rule with the same displayName.

        Returns a DeploymentResult on success or definitive failure, or None
        to signal that the caller should try the next Graph endpoint.
        """
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        # 1. Try PATCH first if we already have the Graph-safe rule ID.
        #    This covers the common case where a previous run created the rule.
        if graph_rule_id:
            patch_url = f"{base_endpoint.rstrip('/')}/{graph_rule_id}"
            try:
                logger.info('[%s] Trying PATCH (known ID): %s', self.PLATFORM_NAME, patch_url)
                resp = requests.patch(patch_url, json=payload, headers=headers, timeout=30)
                if 200 <= resp.status_code < 300:
                    data = resp.json() if resp.content else {}
                    rule_id = str(data.get('id', '')) or graph_rule_id
                    return DeploymentResult(
                        platform=self.PLATFORM_NAME, success=True, rule_id=rule_id,
                        message=f'Custom detection rule updated successfully (ID: {rule_id})',
                    )
                # 404 means it doesn't exist under this ID → fall through to POST.
                if resp.status_code != 404:
                    excerpt = (resp.text or '').strip().replace('\n', ' ')[:500]
                    logger.warning('[%s] PATCH %s returned HTTP %s: %s', self.PLATFORM_NAME, patch_url, resp.status_code, excerpt)
            except requests.RequestException as exc:
                logger.warning('[%s] PATCH request failed: %s', self.PLATFORM_NAME, exc)

        # 2. Try POST (create new rule).
        try:
            logger.info('[%s] Trying POST: %s', self.PLATFORM_NAME, base_endpoint)
            resp = requests.post(base_endpoint, json=payload, headers=headers, timeout=30)
            if 200 <= resp.status_code < 300:
                data = resp.json() if resp.content else {}
                rule_id = str(data.get('id', '')) or graph_rule_id
                return DeploymentResult(
                    platform=self.PLATFORM_NAME, success=True, rule_id=rule_id,
                    message=f'Custom detection rule created successfully (ID: {rule_id})',
                )
            post_excerpt = (resp.text or '').strip().replace('\n', ' ')[:800]
            logger.warning('[%s] POST %s returned HTTP %s: %s', self.PLATFORM_NAME, base_endpoint, resp.status_code, post_excerpt)

            # 3. On 5xx/409, look for an existing rule with the same displayName.
            if resp.status_code in (409,) or resp.status_code >= 500:
                existing_id = self._find_graph_rule_by_name(base_endpoint, display_name, token)
                if existing_id:
                    patch_url = f"{base_endpoint.rstrip('/')}/{existing_id}"
                    logger.info('[%s] Found existing rule ID=%s by displayName; attempting PATCH.', self.PLATFORM_NAME, existing_id)
                    try:
                        patch_resp = requests.patch(patch_url, json=payload, headers=headers, timeout=30)
                        if 200 <= patch_resp.status_code < 300:
                            data = patch_resp.json() if patch_resp.content else {}
                            rule_id = str(data.get('id', existing_id))
                            return DeploymentResult(
                                platform=self.PLATFORM_NAME, success=True, rule_id=rule_id,
                                message=f'Custom detection rule updated (recovered by displayName match, ID: {rule_id})',
                            )
                        summary, details = parse_http_error(patch_resp, platform='Microsoft Graph')
                        return DeploymentResult(
                            platform=self.PLATFORM_NAME, success=False,
                            message=f'{summary}. See errors for details.',
                            errors=details,
                        )
                    except requests.RequestException as exc:
                        return DeploymentResult(
                            platform=self.PLATFORM_NAME, success=False,
                            message=f'PATCH to existing rule {existing_id} failed: {exc}',
                            errors=[str(exc)],
                        )

                # No matching rule found — return a rich error that includes the payload.
                summary, details = parse_http_error(resp, platform='Microsoft Graph')
                return DeploymentResult(
                    platform=self.PLATFORM_NAME, success=False,
                    message=f'{summary}. See errors for details.',
                    errors=details,
                )

        except requests.RequestException as exc:
            logger.exception('[%s] POST request exception on %s', self.PLATFORM_NAME, base_endpoint)
            return DeploymentResult(
                platform=self.PLATFORM_NAME, success=False,
                message=f'Request error for POST {base_endpoint}: {exc}',
                errors=[str(exc)],
            )

        # Non-5xx, non-409 error from POST (e.g. 400/401/403) — surface the
        # real Graph error to the caller instead of silently bubbling up None
        # (which previously let the retired-legacy 405 mask the actual cause).
        summary, details = parse_http_error(resp, platform='Microsoft Graph')
        return DeploymentResult(
            platform=self.PLATFORM_NAME, success=False,
            message=f'{summary}. See errors for details.',
            errors=details,
        )

    def _find_graph_rule_by_name(self, base_endpoint: str, display_name: str, token: str) -> 'str | None':
        """GET the detection rules list and return the Graph ID of the first rule matching display_name."""
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
        }
        try:
            resp = requests.get(
                base_endpoint,
                headers=headers,
                params={'$filter': f"displayName eq '{display_name.replace(chr(39), chr(39)*2)}'"},
                timeout=30,
            )
            if resp.ok:
                for rule in resp.json().get('value', []):
                    if rule.get('displayName') == display_name:
                        return str(rule['id'])
            # Fallback: fetch all and scan (in case $filter isn't supported).
            resp2 = requests.get(base_endpoint, headers=headers, timeout=30)
            if resp2.ok:
                for rule in resp2.json().get('value', []):
                    if rule.get('displayName') == display_name:
                        return str(rule['id'])
        except Exception as exc:
            logger.warning('[%s] GET rule list failed: %s', self.PLATFORM_NAME, exc)
        return None

    # ------------------------------------------------------------------
    # Query validation
    # ------------------------------------------------------------------

    def validate_query(self, query: str, rule_data: dict | None = None) -> tuple[bool, list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        q = query.strip()
        if not q:
            errors.append('Query is empty.')
            return False, errors
        if '|' not in q and ' ' not in q:
            errors.append('Query appears too short to be valid KQL.')
            return False, errors

        non_defender_tables = _detect_non_defender_tables(q)
        if non_defender_tables:
            errors.append(
                'KQL query references non-Defender tables: '
                f'{", ".join(non_defender_tables)}. '
                'Use Microsoft Defender Advanced Hunting tables such as '
                'DeviceProcessEvents, DeviceNetworkEvents, or DeviceLogonEvents.'
            )
        elif not _query_references_defender_table(q):
            errors.append(
                'KQL query does not reference any known Microsoft Defender Advanced Hunting table; '
                'the rule will be rejected by Defender with HTTP 400.'
            )

        platforms = rule_data.get('platforms', {}) if isinstance(rule_data, dict) else {}
        kql_block = platforms.get('kql', {}) if isinstance(platforms, dict) else {}
        configurations = rule_data.get('configurations', {}) if isinstance(rule_data, dict) else {}
        defender_conf = (
            configurations.get('defender_for_endpoint', {})
            if isinstance(configurations, dict)
            else {}
        )

        for origin, raw_period in (
            ('platforms.kql.schedule.period', kql_block.get('schedule', {}).get('period') if isinstance(kql_block, dict) and isinstance(kql_block.get('schedule'), dict) else None),
            ('configurations.defender_for_endpoint.schedule.period', defender_conf.get('schedule', {}).get('period') if isinstance(defender_conf, dict) and isinstance(defender_conf.get('schedule'), dict) else None),
        ):
            if raw_period is None or str(raw_period).strip() == '':
                continue
            normalized = _normalize_graph_period(str(raw_period))
            raw = str(raw_period).strip().upper()
            if normalized != raw:
                warnings.append(
                    f'Warning: {origin} value "{raw_period}" will be normalized to "{normalized}" for Microsoft Graph.'
                )

        impacted_entities = defender_conf.get('impacted_entities') if isinstance(defender_conf, dict) else None
        if isinstance(impacted_entities, dict):
            for entity_type in ('device', 'user', 'mailbox'):
                column = impacted_entities.get(entity_type)
                if not column:
                    continue
                column_name = str(column).strip()
                if not column_name:
                    continue
                if re.search(rf'\b{re.escape(column_name)}\b', q) is None:
                    errors.append(
                        f'Declared impacted entity `{entity_type} = {column_name}` is not referenced anywhere in the KQL query. '
                        f'Defender will reject the rule because the column is missing from the query output. '
                        f'Either add `| project {column_name}, ...` to the KQL or change '
                        f'`impacted_entities.{entity_type}` to a column that the query actually projects.'
                    )

        return len(errors) == 0, errors + warnings
