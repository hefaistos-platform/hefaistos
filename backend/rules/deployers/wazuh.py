"""
Wazuh deployment engine.

Authenticates via the Wazuh manager API (JWT) and uploads a custom XML rule
using the Wazuh rules management API.

Required credentials:
    url      – Base URL of the Wazuh manager API, e.g. https://wazuh.example.com:55000
    username – Wazuh API user (default: wazuh-wui)
    password – Wazuh API password
"""

import logging
import xml.etree.ElementTree as ET
import requests

from .base import PlatformDeployer, DeploymentResult, parse_http_error

logger = logging.getLogger(__name__)

_AUTH_URL = '{url}/security/user/authenticate'
_RULES_URL = '{url}/rules/files/{filename}'


class WazuhDeployer(PlatformDeployer):
    """Deploys XML detection rules to Wazuh manager."""

    PLATFORM_NAME = 'Wazuh'

    # ------------------------------------------------------------------
    # Credential validation
    # ------------------------------------------------------------------

    def validate_credentials(self) -> tuple[bool, str]:
        required = ('url', 'username', 'password')
        missing = [k for k in required if not self.credentials.get(k)]
        if missing:
            return False, f"Missing required fields: {', '.join(missing)}"
        return True, ''

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        url = self.credentials['url'].rstrip('/')
        resp = requests.post(
            _AUTH_URL.format(url=url),
            auth=(self.credentials['username'], self.credentials['password']),
            verify=self.credentials.get('verify_ssl', True),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data.get('data', {}).get('token')
        logger.info('[%s] Authenticated successfully.', self.PLATFORM_NAME)
        return bool(self._token)

    # ------------------------------------------------------------------
    # Rule deployment
    # ------------------------------------------------------------------

    def deploy_rule(self, rule_data: dict) -> DeploymentResult:
        url = self.credentials['url'].rstrip('/')
        platforms = rule_data.get('platforms', {})
        wazuh_block = platforms.get('wazuh', {})
        xml_rule = wazuh_block.get('rule', '') if isinstance(wazuh_block, dict) else ''

        if not xml_rule:
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message='No Wazuh XML rule found in OpenTide rule for Wazuh deployment.',
            )

        is_valid, errors = self.validate_query(xml_rule, rule_data)
        if not is_valid:
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message='Wazuh XML rule validation failed.',
                errors=errors,
            )

        metadata = rule_data.get('metadata', {})
        rule_title = metadata.get('title', 'opentide_rule')
        filename = rule_title.lower().replace(' ', '_')[:64] + '.xml'

        # Ensure the XML is wrapped in a <group> element if not already
        stripped = xml_rule.strip()
        if not stripped.startswith('<group'):
            group_name = metadata.get('mitre_technique', 'opentide').replace('.', '_')
            # Wazuh group name attribute uses a comma-terminated list format
            xml_content = f'<group name="{group_name}">\n{stripped}\n</group>'
        else:
            xml_content = stripped

        resp = requests.put(
            _RULES_URL.format(url=url, filename=filename),
            data=xml_content.encode('utf-8'),
            headers={
                'Authorization': f'Bearer {self._token}',
                'Content-Type': 'application/xml',
            },
            params={'overwrite': 'true'},
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
        # Wazuh API wraps success responses in data.affected_items
        affected = result.get('data', {}).get('affected_items', [filename])
        rule_id = affected[0] if affected else filename
        logger.info('[%s] Rule deployed: %s', self.PLATFORM_NAME, rule_id)
        return DeploymentResult(
            platform=self.PLATFORM_NAME,
            success=True,
            rule_id=rule_id,
            message=f'Wazuh rule file uploaded successfully ({rule_id})',
        )

    # ------------------------------------------------------------------
    # Query validation
    # ------------------------------------------------------------------

    def validate_query(self, query: str, rule_data: dict | None = None) -> tuple[bool, list[str]]:
        errors: list[str] = []
        q = query.strip()
        if not q:
            errors.append('Wazuh rule XML is empty.')
            return False, errors

        try:
            root = ET.fromstring(q)
        except ET.ParseError as exc:
            errors.append(f'Wazuh rule XML is not well-formed: {exc}.')
            return False, errors

        root_tag = root.tag.lower() if isinstance(root.tag, str) else ''
        if root_tag not in {'group', 'rule'}:
            errors.append('Wazuh XML must start with a top-level <group> or <rule> element.')

        rule_nodes = [root] if root_tag == 'rule' else list(root.findall('.//rule'))
        if not rule_nodes:
            errors.append('Wazuh rule XML must contain at least one <rule> element.')

        for idx, rule in enumerate(rule_nodes, start=1):
            level = rule.attrib.get('level')
            if level is None:
                errors.append(f'Wazuh <rule> #{idx} is missing required "level" attribute.')
                continue
            try:
                level_int = int(level)
            except ValueError:
                errors.append(f'Wazuh <rule> #{idx} has non-integer level "{level}".')
                continue
            if level_int < 0 or level_int > 16:
                errors.append(f'Wazuh <rule> #{idx} level must be between 0 and 16.')

        return (len(errors) == 0, errors)
