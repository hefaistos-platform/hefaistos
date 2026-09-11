import logging
import os
from django.core.management.base import BaseCommand

from core.email_service import get_email_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send a test email via configured email backend (SMTP preferred, Mailgun fallback)"

    def add_arguments(self, parser):
        parser.add_argument('--to', type=str, required=True, help='Recipient email address')
        parser.add_argument('--check-only', action='store_true', help='Only check configuration, do not send')

    def handle(self, *args, **options):
        recipient = options['to']
        check_only = options.get('check_only', False)
        
        self.stdout.write(self.style.NOTICE("=== Email Configuration Check ==="))
        
        # Check environment variables
        self.stdout.write("\nEnvironment Variables:")
        env_vars = ['MAILGUN_API_KEY', 'MAILGUN_DOMAIN', 'MAILGUN_FROM_EMAIL', 'MAILGUN_API_BASE']
        for var in env_vars:
            value = os.environ.get(var)
            if value:
                # Mask API key
                if 'KEY' in var or 'API' in var:
                    display = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
                else:
                    display = value
                self.stdout.write(self.style.SUCCESS(f"  {var}: {display}"))
            else:
                self.stdout.write(self.style.WARNING(f"  {var}: NOT SET"))
        
        # Check Docker secrets
        self.stdout.write("\nDocker Secrets:")
        secret_path = "/run/secrets/mailgun_api"
        if os.path.exists(secret_path):
            try:
                with open(secret_path, 'r') as f:
                    content = f.read().strip()
                    if content:
                        display = f"{content[:8]}...{content[-4:]}" if len(content) > 12 else "***"
                        self.stdout.write(self.style.SUCCESS(f"  {secret_path}: {display}"))
                    else:
                        self.stdout.write(self.style.ERROR(f"  {secret_path}: EXISTS BUT EMPTY"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  {secret_path}: ERROR reading - {e}"))
        else:
            self.stdout.write(self.style.WARNING(f"  {secret_path}: NOT FOUND"))
        
        # Initialize and check service
        self.stdout.write("\nService Status:")
        service = get_email_service()
        backend_name = type(service).__name__
        
        if service.is_configured():
            self.stdout.write(self.style.SUCCESS(f"  Configured: YES"))
            self.stdout.write(f"  Backend: {backend_name}")
            if hasattr(service, 'domain'):
                self.stdout.write(f"  Domain: {getattr(service, 'domain', '')}")
            if hasattr(service, 'base_url'):
                self.stdout.write(f"  API Base URL: {getattr(service, 'base_url', '')}")
            if hasattr(service, 'smtp_server'):
                self.stdout.write(
                    f"  SMTP Host: {getattr(service, 'smtp_server', '')}:{getattr(service, 'smtp_port', '')}"
                )
                self.stdout.write(f"  Encryption: {getattr(service, 'encryption', '')}")
            if hasattr(service, 'from_email'):
                self.stdout.write(f"  From: {getattr(service, 'from_email', '')}")
        else:
            self.stdout.write(self.style.ERROR(f"  Configured: NO"))
            self.stdout.write(self.style.ERROR("  Cannot send emails - missing SMTP/Mailgun configuration"))
            return
        
        if check_only:
            self.stdout.write(self.style.NOTICE("\n--check-only specified, skipping email send"))
            return

        # Send test email
        self.stdout.write(self.style.NOTICE(f"\n=== Sending Test Email to {recipient} ==="))
        
        subject = 'Hefaistos Test Email'
        text = f'This is a test email from Hefaistos via {backend_name}.'
        html = f'<html><body><h3>Hefaistos Test Email</h3><p>This is a test email via {backend_name}.</p></body></html>'

        ok = service.send_message(to=[recipient], subject=subject, text=text, html=html)
        if ok:
            self.stdout.write(self.style.SUCCESS('\n✓ Test email sent successfully!'))
        else:
            self.stdout.write(self.style.ERROR('\n✗ Failed to send test email.'))
            self.stdout.write(self.style.ERROR('  Check the logs above for error details.'))
            self.stdout.write(self.style.WARNING('\nCommon issues:'))
            self.stdout.write('  - SMTP sender rejected (set SMTP FROM or valid username email)')
            self.stdout.write('  - SMTP auth/encryption mismatch')
            self.stdout.write('  - 401/403/404 for Mailgun key/domain')
