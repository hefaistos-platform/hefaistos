import os
import logging
import re
import smtplib
from email.message import EmailMessage
from typing import List, Optional, Dict, Union

import requests

logger = logging.getLogger(__name__)


def _read_secret_file(name: str) -> Optional[str]:
    """Read a secret from Docker secrets directory."""
    paths_to_try = [
        f"/run/secrets/{name}",
        os.environ.get(f"{name.upper()}_FILE", ""),
    ]
    for path in paths_to_try:
        if path:
            try:
                with open(path, "r") as f:
                    value = f.read().strip()
                    if value:
                        logger.debug(f"Read secret '{name}' from {path}")
                        return value
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.warning(f"Error reading secret file {path}: {e}")
    return None


class MailgunEmailService:
    """
    Simple Mailgun API client. Uses HTTP API (more reliable than SMTP).

    Required configuration (via Docker secrets or env vars):
    - MAILGUN_API_KEY or /run/secrets/mailgun_api
    - MAILGUN_DOMAIN (e.g., mg.hefaistos.org)
    - MAILGUN_FROM_EMAIL (e.g., automaton@hefaistos.org)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        domain: Optional[str] = None,
        from_email: Optional[str] = None,
    ):
        # Prefer Docker secret at /run/secrets/mailgun_api
        secret_key = _read_secret_file("mailgun_api")
        self.api_key = api_key or secret_key or os.environ.get("MAILGUN_API_KEY")
        self.domain = domain or os.environ.get("MAILGUN_DOMAIN")
        self.from_email = from_email or os.environ.get("MAILGUN_FROM_EMAIL")

        # Track what's configured for debugging
        self._configured = bool(self.api_key and self.domain and self.from_email)
        
        if not self._configured:
            missing = []
            if not self.api_key:
                missing.append("MAILGUN_API_KEY (or /run/secrets/mailgun_api)")
            if not self.domain:
                missing.append("MAILGUN_DOMAIN")
            if not self.from_email:
                missing.append("MAILGUN_FROM_EMAIL")
            logger.warning(
                f"MailgunEmailService not fully configured. Missing: {', '.join(missing)}"
            )
        else:
            # Log configuration (mask API key for security)
            api_key_masked = f"{self.api_key[:8]}...{self.api_key[-4:]}" if len(self.api_key or '') > 12 else "***"
            logger.info(
                f"MailgunEmailService initialized: domain={self.domain}, from={self.from_email}, api_key={api_key_masked}"
            )

        api_base = os.environ.get("MAILGUN_API_BASE", "https://api.eu.mailgun.net")
        self.base_url = f"{api_base}/v3/{self.domain}"

    def is_configured(self) -> bool:
        """Check if the service is properly configured."""
        return self._configured

    def _post(self, path: str, data: Dict[str, str], files: Optional[Dict] = None) -> requests.Response:
        if not self._configured:
            raise RuntimeError("MailgunEmailService is not configured. Cannot send requests.")
        
        url = f"{self.base_url}{path}"
        logger.debug(f"Mailgun POST to {url}")
        try:
            resp = requests.post(url, auth=("api", self.api_key), data=data, files=files, timeout=15)
            return resp
        except requests.exceptions.Timeout:
            logger.error(f"Mailgun request timed out: {url}")
            raise
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Mailgun connection error: {e}")
            raise
        except Exception as e:
            logger.exception(f"Mailgun POST error: {e}")
            raise

    def send_message(
        self,
        to: List[str],
        subject: str,
        text: Optional[str] = None,
        html: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        hide_recipients: bool = True,
    ) -> bool:
        """
        Send an email via Mailgun API.
        
        Args:
            to: List of recipient email addresses
            subject: Email subject
            text: Plain text body (optional)
            html: HTML body (optional)
            headers: Additional email headers (optional)
            hide_recipients: If True (default), deliver recipients as BCC.
        
        Returns:
            True if sent successfully, False otherwise
        """
        if not self._configured:
            logger.error("Mailgun send_message called but service is not configured")
            return False
            
        if not to:
            logger.error("Mailgun send_message called with empty recipients list")
            return False
            
        if not text and not html:
            logger.error("Mailgun send_message called without text or html body")
            return False

        data = {
            "from": self.from_email,
            "subject": subject,
        }
        if hide_recipients:
            # Prevent recipients from seeing each other's email addresses.
            data["to"] = self.from_email
            data["bcc"] = ", ".join(to)
        else:
            data["to"] = ", ".join(to)
        if text:
            data["text"] = text
        if html:
            data["html"] = html
        if headers:
            for k, v in headers.items():
                data[f"h:{k}"] = v

        try:
            resp = self._post("/messages", data=data)
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
            
        if 200 <= resp.status_code < 300:
            logger.info(
                f"Mailgun: message sent to {to} (status={resp.status_code})"
            )
            return True
        else:
            body_preview = (resp.text or '')[:500]
            logger.error(
                "Mailgun send failed: status=%s reason=%s url=%s body=%s",
                resp.status_code,
                getattr(resp, 'reason', ''),
                resp.url,
                body_preview
            )
            # Log common error codes with helpful messages
            if resp.status_code == 401:
                logger.error("Mailgun 401: Invalid API key. Check MAILGUN_API_KEY or /run/secrets/mailgun_api")
            elif resp.status_code == 403:
                logger.error("Mailgun 403: API key doesn't have permission for this domain, or domain not verified")
            elif resp.status_code == 404:
                logger.error(f"Mailgun 404: Domain '{self.domain}' not found. Check MAILGUN_DOMAIN configuration")
            return False

    def verify_recipient(self, email: str) -> bool:
        """
        Optional helper to verify/authorize recipient in sandbox.
        For production domains this is typically not needed.
        """
        if not self._configured:
            logger.error("Cannot verify recipient - service not configured")
            return False
            
        url = "https://api.mailgun.net/v5/sandbox/auth_recipients"
        try:
            resp = requests.post(url, auth=("api", self.api_key), params={"email": email}, timeout=15)
            logger.info(f"Mailgun verify recipient {email}: {resp.status_code}")
            return 200 <= resp.status_code < 300
        except Exception as e:
            logger.exception(f"Mailgun verify_recipient error: {e}")
            return False


class SMTPEmailService:
    """SMTP email client loaded from effective organization SMTP settings."""

    def __init__(self, organization=None):
        self.organization = organization
        self.smtp_server = ''
        self.smtp_port = 0
        self.encryption = 'NONE'
        self.login_method = 'PLAIN'
        self.smtp_username = ''
        self.smtp_password = ''
        self.from_email = ''
        self._configured = False
        self._load_settings()

    def _load_settings(self) -> None:
        try:
            from organizations.models import SharedSmtpProfile, get_effective_smtp_for_organization
            settings_obj = None

            # Registration/contact flows are not tied to a specific organization.
            # Prefer platform shared SMTP profile first, then legacy global SMTP.
            if self.organization is None:
                settings_obj = (
                    SharedSmtpProfile.objects.filter(is_active=True, name__iexact='System Shared SMTP')
                    .order_by('-updated_at')
                    .first()
                )
                if settings_obj is None:
                    settings_obj = (
                        SharedSmtpProfile.objects.filter(is_active=True)
                        .order_by('-updated_at', 'name')
                        .first()
                    )

            if settings_obj is None:
                settings_obj = get_effective_smtp_for_organization(
                    self.organization,
                    create_if_missing=False,
                )
        except Exception as exc:
            logger.debug("SMTP settings lookup failed (will fallback to Mailgun): %s", exc)
            settings_obj = None

        if not settings_obj:
            self._configured = False
            return

        self.smtp_server = (settings_obj.smtp_server or '').strip()
        self.smtp_port = int(settings_obj.smtp_port or 0)
        self.encryption = (settings_obj.encryption or 'NONE').upper()
        self.login_method = (settings_obj.login_method or 'PLAIN').upper()
        self.smtp_username = (settings_obj.smtp_username or '').strip()
        self.smtp_password = settings_obj.smtp_password or ''
        self.from_email = (settings_obj.from_email or '').strip()
        self._configured = bool(self.smtp_server and self.smtp_port)

    def is_configured(self) -> bool:
        return self._configured

    @staticmethod
    def _is_valid_sender_email(value: str) -> bool:
        if not value or '@' not in value:
            return False
        local, _, domain = value.rpartition('@')
        if not local or not domain:
            return False
        # Require FQDN-like domain to avoid rejected senders such as noreply@localhost.
        return bool(re.match(r'^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$', domain))

    def _resolve_sender(self) -> str:
        # IMPORTANT: SMTP mode must not inherit Mailgun sender env values.
        # Some SMTP relays require sender ownership matching the authenticated user.
        candidates = [
            self.from_email,
            self.smtp_username if '@' in self.smtp_username else "",
        ]
        for candidate in candidates:
            candidate = (candidate or '').strip()
            if self._is_valid_sender_email(candidate):
                return candidate

        host = (self.smtp_server or '').strip().strip('.')
        if re.match(r'^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$', host):
            derived = f"noreply@{host}"
            if self._is_valid_sender_email(derived):
                return derived

        return "noreply@localhost.localdomain"

    def _connect(self):
        timeout_seconds = 20
        if self.encryption == 'SSL':
            server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=timeout_seconds)
        else:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=timeout_seconds)
            server.ehlo()
            if self.encryption == 'STARTTLS':
                server.starttls()
                server.ehlo()

        if self.login_method == 'LOGIN':
            server.login(self.smtp_username, self.smtp_password)
        return server

    def send_message(
        self,
        to: List[str],
        subject: str,
        text: Optional[str] = None,
        html: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        hide_recipients: bool = True,
    ) -> bool:
        if not self._configured:
            logger.error("SMTP send_message called but SMTP service is not configured")
            return False
        if not to:
            logger.error("SMTP send_message called with empty recipients list")
            return False
        if not text and not html:
            logger.error("SMTP send_message called without text or html body")
            return False

        sender = self._resolve_sender()

        def _build_message(from_addr: str) -> EmailMessage:
            msg = EmailMessage()
            msg["From"] = from_addr
            msg["To"] = "undisclosed-recipients: ;" if hide_recipients else ", ".join(to)
            msg["Subject"] = subject
            if headers:
                for key, value in headers.items():
                    msg[key] = value
            if text and html:
                msg.set_content(text)
                msg.add_alternative(html, subtype='html')
            elif html:
                msg.set_content(html, subtype='html')
            else:
                msg.set_content(text or '')
            return msg

        try:
            message = _build_message(sender)
            with self._connect() as server:
                if hide_recipients:
                    server.send_message(message, to_addrs=to)
                else:
                    server.send_message(message)
            logger.info("SMTP: message sent to %s via %s:%s", to, self.smtp_server, self.smtp_port)
            return True
        except smtplib.SMTPRecipientsRefused as exc:
            # Common policy: authenticated user may only send as own address.
            username_sender = (self.smtp_username or '').strip()
            if (
                '@' in username_sender
                and username_sender != sender
                and any(code == 553 for code, _ in exc.recipients.values())
            ):
                logger.warning(
                    "SMTP sender rejected for %s; retrying with authenticated username sender %s",
                    sender,
                    username_sender,
                )
                try:
                    retry_message = _build_message(username_sender)
                    with self._connect() as server:
                        if hide_recipients:
                            server.send_message(retry_message, to_addrs=to)
                        else:
                            server.send_message(retry_message)
                    logger.info(
                        "SMTP: message sent to %s via %s:%s using username sender",
                        to,
                        self.smtp_server,
                        self.smtp_port,
                    )
                    return True
                except Exception:
                    logger.exception("SMTP retry with username sender failed")
                    return False
            logger.exception("SMTP recipients refused: %s", exc)
            return False
        except Exception as exc:
            logger.exception("SMTP send failed: %s", exc)
            return False


def get_email_service(organization=None) -> Union[SMTPEmailService, MailgunEmailService]:
    """Return SMTP service when configured, otherwise fallback to Mailgun."""
    smtp_service = SMTPEmailService(organization=organization)
    if smtp_service.is_configured():
        return smtp_service
    return MailgunEmailService()
