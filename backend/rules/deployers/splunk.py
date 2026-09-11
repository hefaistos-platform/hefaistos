"""
Splunk Enterprise / Splunk Cloud deployment engine.

Authenticates using a Splunk API token (or username/password) and creates /
updates a saved search (correlation search) via the Splunk REST API.

Required credentials:
    url        – Base URL of the Splunk instance, e.g. https://splunk.example.com:8089
    api_token  – Splunk API token (preferred)
    -- OR --
    username   – Splunk username
    password   – Splunk password
"""

import logging
import requests
from requests.auth import HTTPBasicAuth

from .base import PlatformDeployer, DeploymentResult, parse_http_error

logger = logging.getLogger(__name__)


class SplunkDeployer(PlatformDeployer):
    """Deploys SPL saved-search correlation rules to Splunk."""

    PLATFORM_NAME = 'Splunk'

    # ------------------------------------------------------------------
    # Credential validation
    # ------------------------------------------------------------------

    def validate_credentials(self) -> tuple[bool, str]:
        if not self.credentials.get('url'):
            return False, 'Missing required field: url'
        has_token = bool(self.credentials.get('api_token'))
        has_basic = bool(self.credentials.get('username')) and bool(self.credentials.get('password'))
        if not (has_token or has_basic):
            return False, 'Either api_token or username+password must be provided'
        return True, ''

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        url = self.credentials['url'].rstrip('/')
        api_token = self.credentials.get('api_token')

        if api_token:
            # Token-based auth – validate by hitting /services/authentication/current-context
            resp = requests.get(
                f'{url}/services/authentication/current-context',
                headers={'Authorization': f'Bearer {api_token}'},
                params={'output_mode': 'json'},
                verify=self.credentials.get('verify_ssl', True),
                timeout=30,
            )
            resp.raise_for_status()
            self._token = api_token
        else:
            # Basic auth – obtain session key
            resp = requests.post(
                f'{url}/services/auth/login',
                data={
                    'username': self.credentials['username'],
                    'password': self.credentials['password'],
                    'output_mode': 'json',
                },
                verify=self.credentials.get('verify_ssl', True),
                timeout=30,
            )
            resp.raise_for_status()
            self._token = resp.json().get('sessionKey')

        logger.info('[%s] Authenticated successfully.', self.PLATFORM_NAME)
        return bool(self._token)

    # ------------------------------------------------------------------
    # Rule deployment
    # ------------------------------------------------------------------

    def deploy_rule(self, rule_data: dict) -> DeploymentResult:
        url = self.credentials['url'].rstrip('/')
        platforms = rule_data.get('platforms', {})
        spl_block = platforms.get('spl', {})
        query = spl_block.get('query', '') if isinstance(spl_block, dict) else ''

        if not query:
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message='No SPL query found in OpenTide rule for Splunk deployment.',
            )

        is_valid, errors = self.validate_query(query, rule_data)
        if not is_valid:
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message='SPL query validation failed.',
                errors=errors,
            )

        metadata = rule_data.get('metadata', {})
        search_name = metadata.get('title', 'OpenTide Rule')
        index = spl_block.get('index', '*') if isinstance(spl_block, dict) else '*'

        # Build the saved-search API call
        api_token = self.credentials.get('api_token')
        auth_header: dict = (
            {'Authorization': f'Bearer {api_token}'}
            if api_token
            else {'Authorization': f'Splunk {self._token}'}
        )

        resp = requests.post(
            f'{url}/servicesNS/nobody/search/saved/searches',
            data={
                'name': search_name,
                'search': query,
                'description': metadata.get('description', ''),
                'is_scheduled': '1',
                'cron_schedule': '*/5 * * * *',
                'alert_type': 'number of events',
                'alert_comparator': 'greater than',
                'alert_threshold': '0',
                'output_mode': 'json',
            },
            headers=auth_header,
            verify=self.credentials.get('verify_ssl', True),
            timeout=30,
        )

        if resp.status_code == 409:
            # Already exists – update instead
            resp = requests.post(
                f'{url}/servicesNS/nobody/search/saved/searches/{requests.utils.quote(search_name, safe="")}',
                data={'search': query, 'output_mode': 'json'},
                headers=auth_header,
                verify=self.credentials.get('verify_ssl', True),
                timeout=30,
            )

        elif not (200 <= resp.status_code < 300):
            summary, details = parse_http_error(resp, platform=self.PLATFORM_NAME)
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message=f'{summary}. See errors for details.',
                errors=details,
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
        try:
            entry = result.get('entry', [{}])[0]
            rule_id = entry.get('name', search_name)
        except (IndexError, AttributeError):
            rule_id = search_name

        logger.info('[%s] Rule deployed: %s', self.PLATFORM_NAME, rule_id)
        return DeploymentResult(
            platform=self.PLATFORM_NAME,
            success=True,
            rule_id=rule_id,
            message=f'Saved search created/updated successfully (name: {rule_id})',
        )

    # ------------------------------------------------------------------
    # Query validation
    # ------------------------------------------------------------------

    def validate_query(self, query: str, rule_data: dict | None = None) -> tuple[bool, list[str]]:
        errors: list[str] = []
        q = query.strip()
        if not q:
            errors.append('Query is empty.')
            return False, errors

        lower = q.lower()
        if not (lower.startswith('search') or lower.startswith('|')):
            errors.append(
                'SPL query should start with "search" or "|" so Splunk parses it as a search expression.'
            )

        for quote in ('"', "'"):
            count = 0
            escaped = False
            for ch in q:
                if ch == '\\' and not escaped:
                    escaped = True
                    continue
                if ch == quote and not escaped:
                    count += 1
                escaped = False
            if count % 2 != 0:
                errors.append(f'SPL query has unbalanced {quote} quotes.')

        paren_balance = 0
        for ch in q:
            if ch == '(':
                paren_balance += 1
            elif ch == ')':
                paren_balance -= 1
            if paren_balance < 0:
                errors.append('SPL query has unmatched closing parenthesis.')
                break
        if paren_balance > 0:
            errors.append('SPL query has unmatched opening parenthesis.')

        return (len(errors) == 0, errors)
