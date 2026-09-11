"""
User-configurable settings for HEFAISTOS deployment.

Edit this file to customize your deployment-specific settings without
modifying core system files.  This file is imported by backend/core/settings.py.

Priority order (highest to lowest):
  1. Docker secrets  (/run/secrets/<name>)
  2. Environment variables  (set in docker-compose.yml or the shell)
  3. Values defined in this file  (the defaults you set here)
"""

# ---------------------------------------------------------------------------
# Email / SMTP Configuration
# ---------------------------------------------------------------------------
# Configure these settings to enable email notifications (e.g. news digests,
# password-reset emails).  If you prefer, you can override any of these
# values via environment variables or Docker secrets instead - those always
# take precedence over what is written here.
#
# Supported environment variables (set in docker-compose.yml):
#   EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD,
#   EMAIL_USE_TLS, EMAIL_USE_SSL, DEFAULT_FROM_EMAIL
#
# Supported Docker secret (place in .secrets/):
#   email_password  →  maps to EMAIL_HOST_PASSWORD

EMAIL_CONFIGURATION = {
    'EMAIL_HOST': 'smtp.example.com',
    'EMAIL_PORT': 587,
    'EMAIL_USE_TLS': True,
    'EMAIL_USE_SSL': False,
    'DEFAULT_FROM_EMAIL': 'noreply@example.com',
}

# ---------------------------------------------------------------------------
# Mailgun-specific settings (optional)
# ---------------------------------------------------------------------------
# Used by the MailgunEmailService in backend/core/email_service.py.
# Set MAILGUN_API_KEY via a Docker secret named 'mailgun_api' or the
# MAILGUN_API_KEY environment variable.

MAILGUN_CONFIGURATION = {
    'MAILGUN_API_BASE': 'https://api.eu.mailgun.net',
    'MAILGUN_DOMAIN': 'mg.example.com',
    'MAILGUN_FROM_EMAIL': 'noreply@example.com',
}

# ---------------------------------------------------------------------------
# Add other deployment-specific settings below
# ---------------------------------------------------------------------------
