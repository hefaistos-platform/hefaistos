"""
Abstract base class for platform deployment engines.

All platform-specific deployers must inherit from PlatformDeployer and implement
the abstract methods defined here.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class DeploymentResult:
    """Structured result returned by every deployer."""

    platform: str
    success: bool
    rule_id: str | None = None
    message: str = ''
    errors: list[str] = field(default_factory=list)


def _trim_text(value: object, limit: int = 800) -> str:
    text = str(value or '').strip().replace('\n', ' ')
    if len(text) > limit:
        return text[:limit].rstrip() + '...'
    return text


def parse_http_error(response, *, platform: str) -> tuple[str, list[str]]:
    """Parse common platform HTTP error envelopes into summary + details."""
    status = getattr(response, 'status_code', 'unknown')

    try:
        body = response.json()
    except Exception:
        body_text = _trim_text(getattr(response, 'text', '') or '<empty response body>')
        return (f'HTTP {status}', [body_text])

    details: list[str] = []

    # Microsoft Graph envelope.
    if isinstance(body, dict) and isinstance(body.get('error'), dict):
        error = body['error']
        code = _trim_text(error.get('code'))
        message = _trim_text(error.get('message'))
        if message:
            details.append(message)
        # ARM-style details list: {"error":{"details":[{"code":...,"message":...}]}}
        if isinstance(error.get('details'), list):
            for item in error['details']:
                if not isinstance(item, dict):
                    continue
                item_target = _trim_text(item.get('target'))
                item_message = _trim_text(item.get('message'))
                item_code = _trim_text(item.get('code'))
                payload = item_message or item_code
                if not payload:
                    continue
                if item_target:
                    details.append(f'{item_target}: {payload}')
                elif item_code and item_message:
                    details.append(f'{item_code}: {item_message}')
                else:
                    details.append(payload)
        inner = error.get('innerError')
        if isinstance(inner, dict) and isinstance(inner.get('details'), list):
            for item in inner['details']:
                if not isinstance(item, dict):
                    continue
                target = _trim_text(item.get('target'))
                item_message = _trim_text(item.get('message'))
                item_code = _trim_text(item.get('code'))
                payload = item_message or item_code
                if not payload:
                    continue
                details.append(f'{target}: {payload}' if target else payload)
        summary = f'{platform} rejected the rule (HTTP {status}'
        if code:
            summary += f' - {code}'
        summary += ')'
        return summary, details or [_trim_text(json.dumps(body, ensure_ascii=False))]

    # Splunk envelope.
    if isinstance(body, dict) and isinstance(body.get('messages'), list):
        for item in body.get('messages', []):
            if isinstance(item, dict):
                text = _trim_text(item.get('text'))
                typ = _trim_text(item.get('type'))
                if text:
                    details.append(f'{typ}: {text}' if typ else text)
        return (
            f'{platform} rejected the rule (HTTP {status})',
            details or [_trim_text(json.dumps(body, ensure_ascii=False))],
        )

    # Wazuh envelope.
    if isinstance(body, dict) and ('error' in body or 'data' in body):
        message = _trim_text(body.get('message'))
        if message:
            details.append(message)
        error_obj = body.get('error')
        if isinstance(error_obj, dict):
            err_code = _trim_text(error_obj.get('code'))
            err_msg = _trim_text(error_obj.get('message'))
            if err_msg:
                details.append(f'{err_code}: {err_msg}' if err_code else err_msg)
        data = body.get('data')
        if isinstance(data, dict) and isinstance(data.get('failed_items'), list):
            for item in data.get('failed_items', []):
                if not isinstance(item, dict):
                    continue
                err = item.get('error')
                if not isinstance(err, dict):
                    continue
                err_msg = _trim_text(err.get('message'))
                err_code = _trim_text(err.get('code'))
                if err_msg:
                    details.append(f'{err_code}: {err_msg}' if err_code else err_msg)
        return (
            f'{platform} rejected the rule (HTTP {status})',
            details or [_trim_text(json.dumps(body, ensure_ascii=False))],
        )

    # QRadar envelope.
    if isinstance(body, dict) and any(k in body for k in ('code', 'description', 'details', 'message')):
        code = _trim_text(body.get('code'))
        description = _trim_text(body.get('description') or body.get('message'))
        details_obj = body.get('details')
        if description:
            details.append(description)
        if isinstance(details_obj, dict):
            line = details_obj.get('line')
            column = details_obj.get('column')
            if line is not None and column is not None:
                details.append(f'Location: line {line}, column {column}')
            serialized = _trim_text(json.dumps(details_obj, ensure_ascii=False))
            if serialized and serialized != '{}':
                details.append(f'details: {serialized}')
        summary = f'{platform} rejected the rule (HTTP {status}'
        if code:
            summary += f' - code {code}'
        summary += ')'
        return summary, details or [_trim_text(json.dumps(body, ensure_ascii=False))]

    # Generic JSON fallback.
    return (
        f'{platform} rejected the rule (HTTP {status})',
        [_trim_text(json.dumps(body, ensure_ascii=False))],
    )


class PlatformDeployer(ABC):
    """
    Abstract base class for SIEM/EDR platform deployment engines.

    Each concrete deployer must implement:
    - validate_credentials()
    - authenticate()
    - deploy_rule(rule_data)
    - validate_query(query)
    """

    #: Override in subclass – human-readable platform name
    PLATFORM_NAME: str = 'Unknown Platform'

    def __init__(self, credentials: dict) -> None:
        """
        Initialise the deployer with a credentials dict retrieved from
        the encrypted ``PlatformCredential`` model.
        """
        self.credentials = credentials
        self._token: str | None = None

    # ------------------------------------------------------------------
    # Abstract interface – must be implemented by concrete deployers
    # ------------------------------------------------------------------

    @abstractmethod
    def validate_credentials(self) -> tuple[bool, str]:
        """
        Verify that the required credential keys are present and non-empty.

        Returns:
            (is_valid, error_message)
        """

    @abstractmethod
    def authenticate(self) -> bool:
        """
        Obtain an access token / session.  Sets ``self._token`` on success.

        Returns:
            True if authentication succeeded, False otherwise.

        Raises:
            Exception: if a fatal error prevents authentication.
        """

    @abstractmethod
    def deploy_rule(self, rule_data: dict) -> DeploymentResult:
        """
        Deploy an OpenTide rule to the target platform.

        Args:
            rule_data: Parsed OpenTide YAML dict (top-level keys: metadata, platforms).

        Returns:
            DeploymentResult with success flag, optional rule_id, and message.
        """

    @abstractmethod
    def validate_query(self, query: str, rule_data: dict | None = None) -> tuple[bool, list[str]]:
        """
        Validate platform-specific query syntax without deploying.

        Args:
            query: Query string (KQL / SPL / AQL / XML, depending on platform).

        Returns:
            (is_valid, list_of_error_messages)
        """

    # ------------------------------------------------------------------
    # Convenience helper
    # ------------------------------------------------------------------

    def run(self, rule_data: dict) -> DeploymentResult:
        """
        Orchestrate the full deployment cycle:
        1. validate_credentials
        2. authenticate
        3. deploy_rule

        Returns DeploymentResult regardless of outcome.
        """
        is_valid, cred_error = self.validate_credentials()
        if not is_valid:
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message=f'Credential validation failed: {cred_error}',
            )

        try:
            authenticated = self.authenticate()
        except Exception as exc:
            logger.error('[%s] Authentication error: %s', self.PLATFORM_NAME, exc)
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message=f'Authentication error: {exc}',
            )

        if not authenticated:
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message='Authentication failed',
            )

        try:
            return self.deploy_rule(rule_data)
        except Exception as exc:
            logger.error('[%s] Deployment error: %s', self.PLATFORM_NAME, exc)
            return DeploymentResult(
                platform=self.PLATFORM_NAME,
                success=False,
                message=f'Deployment error: {exc}',
            )
