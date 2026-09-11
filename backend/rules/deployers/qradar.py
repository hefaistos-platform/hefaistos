"""
IBM QRadar deployment engine.

Authenticates using a QRadar API token (SEC header) and creates / updates
a Custom Rule via the QRadar REST API.

Required credentials:
    url        – Base URL of the QRadar console, e.g. https://qradar.example.com
    api_token  – QRadar SEC token (user token or authorized service token)
    api_version – QRadar API version, e.g. "18.0" (optional, defaults to "18.0")
"""

import logging
import re
import requests

from .base import PlatformDeployer, DeploymentResult, parse_http_error

logger = logging.getLogger(__name__)

_DEFAULT_API_VERSION = '18.0'


class QRadarDeployer(PlatformDeployer):
    """Deploys AQL-based rules to IBM QRadar."""

    PLATFORM_NAME = 'IBM QRadar'

    # ------------------------------------------------------------------
    # Credential validation
    # ------------------------------------------------------------------

    def validate_credentials(self) -> tuple[bool, str]:
        required = ('url', 'api_token')
        missing = [k for k in required if not self.credentials.get(k)]
        if missing:
            return False, f"Missing required fields: {', '.join(missing)}"
        return True, ''

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        url = self.credentials['url'].rstrip('/')
        api_version = self.credentials.get('api_version', _DEFAULT_API_VERSION)

        resp = requests.get(
            f'{url}/api/help/versions',
            headers={
                'SEC': self.credentials['api_token'],
                'Version': api_version,
                'Accept': 'application/json',
            },
            verify=self.credentials.get('verify_ssl', True),
            timeout=30,
        )
        resp.raise_for_status()
        self._token = self.credentials['api_token']
        logger.info('[%s] Authenticated successfully.', self.PLATFORM_NAME)
        return True

    # ------------------------------------------------------------------
    # Rule deployment
    # ------------------------------------------------------------------

    def deploy_rule(self, rule_data: dict) -> DeploymentResult:
        url = self.credentials['url'].rstrip('/')
        api_version = self.credentials.get('api_version', _DEFAULT_API_VERSION)
        platforms = rule_data.get('platforms', {})
        qradar_block = platforms.get('qradar', {})
        query = qradar_block.get('query', '') if isinstance(qradar_block, dict) else ''

        if not query:
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message='No AQL query found in OpenTide rule for QRadar deployment.',
            )

        is_valid, errors = self.validate_query(query, rule_data)
        if not is_valid:
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message='AQL query validation failed.',
                errors=errors,
            )

        metadata = rule_data.get('metadata', {})
        headers = {
            'SEC': self._token,
            'Version': api_version,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

        # Use the Analytics Rules endpoint for custom detection rules.
        # The AQL query predicate is stored in the rule notes so that it is
        # preserved on the QRadar side and can be inspected by analysts; the
        # full query is also included via the `notes` field because the
        # /api/analytics/rules endpoint does not accept a structured query body.
        payload = {
            'name': metadata.get('title', 'OpenTide Rule'),
            'notes': f"{metadata.get('description', '')}\n\nAQL query:\n{query}".strip(),
            'enabled': True,
            'origin': 'USER',
            'type': 'COMMON',
            'averageCapacity': 0,
            'baseCapacity': 0,
            'capacityTimestamp': 0,
            'linkedRuleIdentifier': None,
        }

        resp = requests.post(
            f'{url}/api/analytics/rules',
            json=payload,
            headers=headers,
            verify=self.credentials.get('verify_ssl', True),
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

        result = resp.json()
        rule_id = str(result.get('id', ''))
        logger.info('[%s] Rule deployed: %s', self.PLATFORM_NAME, rule_id)
        return DeploymentResult(
            platform=self.PLATFORM_NAME,
            success=True,
            rule_id=rule_id,
            message=f'Custom rule created successfully (ID: {rule_id})',
        )

    # ------------------------------------------------------------------
    # Query validation
    # ------------------------------------------------------------------

    def validate_query(self, query: str, rule_data: dict | None = None) -> tuple[bool, list[str]]:
        errors: list[str] = []
        q = query.strip()
        if not q:
            errors.append('AQL query is empty.')
            return False, errors

        upper = q.upper()
        if not upper.startswith('SELECT'):
            errors.append('QRadar AQL query must start with SELECT.')
        if ' FROM ' not in f' {upper} ':
            errors.append('QRadar AQL query must contain a FROM clause.')
        if q.endswith(';'):
            errors.append('QRadar AQL query must not end with a semicolon.')
        if re.search(r'\bfrom\s+events\b', q):
            errors.append(
                'QRadar AQL table should be EVENTS (uppercase), not lowercase "events".'
            )
        return (len(errors) == 0, errors)
