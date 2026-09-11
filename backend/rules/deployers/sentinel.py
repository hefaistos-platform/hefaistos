"""
Azure Sentinel (Microsoft Sentinel) deployment engine.

Authenticates via OAuth 2.0 client_credentials flow and creates / upserts
Scheduled Query Rule (analytics rule) via the Azure Monitor / Sentinel REST API.

Required credentials:
    tenant_id      – Azure AD tenant ID
    client_id      – App registration client ID
    client_secret  – App registration client secret
    subscription_id – Azure subscription ID
    resource_group  – Resource group name
    workspace_name  – Log Analytics workspace name
"""

import logging
import re
import requests

from .base import PlatformDeployer, DeploymentResult, parse_http_error

logger = logging.getLogger(__name__)

_TOKEN_URL = 'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'
_SCOPE = 'https://management.azure.com/.default'
_RULE_URL = (
    'https://management.azure.com'
    '/subscriptions/{subscription_id}'
    '/resourceGroups/{resource_group}'
    '/providers/Microsoft.OperationalInsights'
    '/workspaces/{workspace_name}'
    '/providers/Microsoft.SecurityInsights'
    '/alertRules/{rule_id}'
    '?api-version=2022-12-01-preview'
)
_SENTINEL_QUERY_LIMIT = 10000
_ALLOWED_TRIGGER_OPERATORS = {'GreaterThan', 'LessThan', 'Equal', 'NotEqual'}
_ISO8601_DURATION_RE = re.compile(
    r'^P(?!$)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(\d+H)?(\d+M)?(\d+S)?)?$',
    re.IGNORECASE,
)


def _is_iso8601_duration(value: object) -> bool:
    return isinstance(value, str) and bool(_ISO8601_DURATION_RE.match(value.strip()))


def _parse_bool(value: object) -> tuple[bool, bool]:
    if isinstance(value, bool):
        return value, True
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'true', '1', 'yes', 'on'}:
            return True, True
        if normalized in {'false', '0', 'no', 'off'}:
            return False, True
    return False, False


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def _extract_sentinel_cfg(rule_data: dict) -> dict:
    cfg: dict = {}
    if not isinstance(rule_data, dict):
        return cfg

    configurations = rule_data.get('configurations')
    if isinstance(configurations, dict):
        sentinel_cfg = configurations.get('microsoft_sentinel')
        if isinstance(sentinel_cfg, dict):
            cfg.update(sentinel_cfg)

    platforms = rule_data.get('platforms')
    if isinstance(platforms, dict):
        kql_block = platforms.get('kql')
        if isinstance(kql_block, dict):
            if 'query' not in cfg and isinstance(kql_block.get('query'), str):
                cfg['query'] = kql_block.get('query')

    return cfg


class SentinelDeployer(PlatformDeployer):
    """Deploys KQL analytics rules to Azure Sentinel."""

    PLATFORM_NAME = 'Azure Sentinel'

    # ------------------------------------------------------------------
    # Credential validation
    # ------------------------------------------------------------------

    def validate_credentials(self) -> tuple[bool, str]:
        required = ('tenant_id', 'client_id', 'client_secret',
                    'subscription_id', 'resource_group', 'workspace_name')
        missing = [k for k in required if not self.credentials.get(k)]
        if missing:
            return False, f"Missing required fields: {', '.join(missing)}"
        return True, ''

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        tenant_id = self.credentials['tenant_id']
        resp = requests.post(
            _TOKEN_URL.format(tenant_id=tenant_id),
            data={
                'grant_type': 'client_credentials',
                'client_id': self.credentials['client_id'],
                'client_secret': self.credentials['client_secret'],
                'scope': _SCOPE,
            },
            timeout=30,
        )
        resp.raise_for_status()
        self._token = resp.json().get('access_token')
        logger.info('[%s] Authenticated successfully.', self.PLATFORM_NAME)
        return bool(self._token)

    # ------------------------------------------------------------------
    # Rule deployment
    # ------------------------------------------------------------------

    def deploy_rule(self, rule_data: dict) -> DeploymentResult:
        import uuid as _uuid

        sentinel_cfg = _extract_sentinel_cfg(rule_data)
        query = sentinel_cfg.get('query', '') if isinstance(sentinel_cfg.get('query'), str) else ''

        if not query:
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message='No KQL query found in OpenTide rule for Sentinel deployment.',
            )

        is_valid, errors = self.validate_query(query, rule_data)
        if not is_valid:
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message='KQL query validation failed.',
                errors=errors,
            )

        metadata = rule_data.get('metadata', {})
        rule_uuid = str(metadata.get('uuid', _uuid.uuid4()))
        severity_map = {
            'CRITICAL': 'High',
            'HIGH': 'High',
            'MEDIUM': 'Medium',
            'LOW': 'Low',
        }
        severity = severity_map.get(
            str(sentinel_cfg.get('severity') or metadata.get('severity', 'MEDIUM')).upper(),
            'Medium',
        )

        trigger_threshold = sentinel_cfg.get('triggerThreshold', 0)
        try:
            trigger_threshold = int(trigger_threshold)
        except (TypeError, ValueError):
            trigger_threshold = 0

        suppression_enabled, suppression_enabled_valid = _parse_bool(
            sentinel_cfg.get('suppressionEnabled', False)
        )
        if not suppression_enabled_valid:
            suppression_enabled = False

        enabled, enabled_valid = _parse_bool(sentinel_cfg.get('enabled', True))
        if not enabled_valid:
            status = str(sentinel_cfg.get('status', 'PRODUCTION')).strip().upper()
            enabled = status not in {'DISABLED', 'INACTIVE'}

        payload = {
            'kind': 'Scheduled',
            'properties': {
                'displayName': sentinel_cfg.get('displayName') or metadata.get('title', 'OpenTide Rule'),
                'description': sentinel_cfg.get('description') or metadata.get('description', ''),
                'severity': severity,
                'enabled': enabled,
                'query': query,
                'queryFrequency': sentinel_cfg.get('queryFrequency', 'PT5H'),
                'queryPeriod': sentinel_cfg.get('queryPeriod', 'P1D'),
                'triggerOperator': sentinel_cfg.get('triggerOperator', 'GreaterThan'),
                'triggerThreshold': trigger_threshold,
                'suppressionDuration': sentinel_cfg.get('suppressionDuration', 'PT1H'),
                'suppressionEnabled': suppression_enabled,
            },
        }
        for key in (
            'tactics',
            'techniques',
            'eventGroupingSettings',
            'incidentConfiguration',
            'alertDetailsOverride',
            'customDetails',
            'entityMappings',
        ):
            if key in sentinel_cfg:
                payload['properties'][key] = sentinel_cfg[key]

        url = _RULE_URL.format(
            subscription_id=self.credentials['subscription_id'],
            resource_group=self.credentials['resource_group'],
            workspace_name=self.credentials['workspace_name'],
            rule_id=rule_uuid,
        )

        resp = requests.put(
            url,
            json=payload,
            headers={
                'Authorization': f'Bearer {self._token}',
                'Content-Type': 'application/json',
            },
            timeout=30,
        )
        if not (200 <= resp.status_code < 300):
            summary, details = parse_http_error(resp, platform=self.PLATFORM_NAME)
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message=f'{summary}. See errors for details.',
                errors=details,
            )

        logger.info('[%s] Rule deployed: %s', self.PLATFORM_NAME, rule_uuid)
        return DeploymentResult(
            platform=self.PLATFORM_NAME,
            success=True,
            rule_id=rule_uuid,
            message=f'Analytics rule deployed successfully (ID: {rule_uuid})',
        )

    # ------------------------------------------------------------------
    # Query validation
    # ------------------------------------------------------------------

    def validate_query(self, query: str, rule_data: dict | None = None) -> tuple[bool, list[str]]:
        errors: list[str] = []
        q = query.strip()
        if not q:
            errors.append('Query is empty.')
        if len(q) > _SENTINEL_QUERY_LIMIT:
            errors.append(
                f'Sentinel KQL query exceeds {_SENTINEL_QUERY_LIMIT} characters and will be rejected.'
            )

        sentinel_cfg = _extract_sentinel_cfg(rule_data or {})
        if sentinel_cfg:
            frequency = sentinel_cfg.get('queryFrequency')
            if frequency is not None and not _is_iso8601_duration(frequency):
                errors.append('queryFrequency must be a valid ISO 8601 duration (e.g. PT5M, PT1H).')

            period = sentinel_cfg.get('queryPeriod')
            if period is not None and not _is_iso8601_duration(period):
                errors.append('queryPeriod must be a valid ISO 8601 duration (e.g. P1D, PT6H).')

            operator = sentinel_cfg.get('triggerOperator')
            if operator is not None and operator not in _ALLOWED_TRIGGER_OPERATORS:
                errors.append(
                    'triggerOperator must be one of: '
                    + ', '.join(sorted(_ALLOWED_TRIGGER_OPERATORS))
                    + '.'
                )

            threshold = sentinel_cfg.get('triggerThreshold')
            if threshold is not None:
                try:
                    threshold_value = int(threshold)
                    if threshold_value < 0:
                        errors.append('triggerThreshold must be >= 0.')
                except (TypeError, ValueError):
                    errors.append('triggerThreshold must be an integer.')

            suppression_duration = sentinel_cfg.get('suppressionDuration')
            if suppression_duration is not None and not _is_iso8601_duration(suppression_duration):
                errors.append(
                    'suppressionDuration must be a valid ISO 8601 duration '
                    '(e.g. PT1H, PT30M).'
                )

            if 'suppressionEnabled' in sentinel_cfg:
                _, suppression_valid = _parse_bool(sentinel_cfg.get('suppressionEnabled'))
                if not suppression_valid:
                    errors.append('suppressionEnabled must be a boolean value.')

            if 'tactics' in sentinel_cfg and not _is_string_list(sentinel_cfg.get('tactics')):
                errors.append('tactics must be a non-empty list of strings.')

            if 'techniques' in sentinel_cfg and not _is_string_list(sentinel_cfg.get('techniques')):
                errors.append('techniques must be a non-empty list of strings.')

            custom_details = sentinel_cfg.get('customDetails')
            if custom_details is not None:
                if not isinstance(custom_details, dict):
                    errors.append('customDetails must be an object/dictionary.')
                elif any(not isinstance(k, str) or not isinstance(v, str) for k, v in custom_details.items()):
                    errors.append('customDetails keys and values must be strings.')

            if 'entityMappings' in sentinel_cfg and not isinstance(sentinel_cfg.get('entityMappings'), list):
                errors.append('entityMappings must be a list.')

            event_grouping = sentinel_cfg.get('eventGroupingSettings')
            if event_grouping is not None:
                if not isinstance(event_grouping, dict):
                    errors.append('eventGroupingSettings must be an object/dictionary.')
                elif 'enabled' in event_grouping and not isinstance(event_grouping.get('enabled'), bool):
                    errors.append('eventGroupingSettings.enabled must be a boolean value.')

            incident_cfg = sentinel_cfg.get('incidentConfiguration')
            if incident_cfg is not None and not isinstance(incident_cfg, dict):
                errors.append('incidentConfiguration must be an object/dictionary.')

            alert_details_override = sentinel_cfg.get('alertDetailsOverride')
            if alert_details_override is not None and not isinstance(alert_details_override, dict):
                errors.append('alertDetailsOverride must be an object/dictionary.')

        return (len(errors) == 0, errors)
