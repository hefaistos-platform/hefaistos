from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken
from django.utils import timezone
from datetime import timedelta
import hashlib
import secrets
from organizations.models import Organization


def _get_fernet():
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
    if not key:
        return None
    try:
        return Fernet(key)
    except Exception:
        return None


def _encrypt(value: str) -> str:
    value = value or ''
    if not value:
        return ''
    if value.startswith('enc:'):
        return value
    f = _get_fernet()
    if not f:
        return value
    return 'enc:' + f.encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    value = value or ''
    if not value:
        return ''
    if not value.startswith('enc:'):
        return value
    token = value[4:]
    f = _get_fernet()
    if not f:
        return ''
    try:
        return f.decrypt(token.encode()).decode()
    except (InvalidToken, Exception):
        return ''


class CustomUser(AbstractUser):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    default_organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='default_users',
    )

    # --- ADD THIS ---
    class Roles(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        RESOURCE_MANAGER = 'RESOURCE_MANAGER', 'Resource Manager'
        ANALYST = 'ANALYST', 'Analyst'
        REVIEWER = 'REVIEWER', 'Reviewer'
        VIEWER = 'VIEWER', 'Viewer'
        ELONE = 'ELONE', 'ElOne'
        BOT_AUDITOR_ORG = 'BOT_AUDITOR_ORG', 'Bot Auditor (Org)'
        BOT_AUDITOR_GLOBAL = 'BOT_AUDITOR_GLOBAL', 'Bot Auditor (Global)'

    role = models.CharField(
        max_length=24,
        choices=Roles.choices,
        default=Roles.ANALYST, # Default new users to 'Analyst'
        help_text="The user's role, which determines their permissions."
    )
    # --- END ADD ---

    # --- PROFILE FIELDS (Phase: User Profiles) ---
    avatar = models.ImageField(
        upload_to='avatars/',
        null=True,
        blank=True,
        help_text="Optional profile avatar image (requires Pillow)."
    )
    bio = models.TextField(
        max_length=500,
        blank=True,
        help_text="Short 'About Me' summary."
    )
    job_title = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g. Senior Threat Hunter"
    )
    slack_handle = models.CharField(
        max_length=50,
        blank=True,
        help_text="Slack username or handle (e.g. @hunter01)"
    )
    session_timeout_hours = models.PositiveSmallIntegerField(
        choices=(
            (2, '2 hours'),
            (4, '4 hours'),
            (8, '8 hours'),
            (12, '12 hours'),
            (24, '24 hours'),
        ),
        default=4,
        help_text="Auto-logout timeout after this many hours of inactivity.",
    )
    # --- END PROFILE FIELDS ---

    # --- EMAIL NOTIFICATION PREFERENCES ---
    email_notify_review_approved = models.BooleanField(
        default=False,
        help_text="Email me when my review is approved"
    )
    email_notify_system_message = models.BooleanField(
        default=False,
        help_text="Email me when there is a new system message"
    )
    email_notify_chat_message = models.BooleanField(
        default=False,
        help_text="Email me when I have a new chat message"
    )
    email_notify_workbench_edited = models.BooleanField(
        default=False,
        help_text="Email me when someone edits my workbench"
    )
    email_notify_news_digest = models.BooleanField(
        default=False,
        help_text="Email me when there is a news digest"
    )
    workbench_visibility_defaults = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per-user workbench section visibility defaults.",
    )

    def __str__(self):
        return self.username


class UserOrganizationMembership(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='organization_memberships')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='user_memberships')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'organization')
        ordering = ['organization__name']

    def __str__(self):
        return f"{self.user.username} -> {self.organization.name}"


class PasswordResetToken(models.Model):
    """One-time token for password reset. Expires after 1 hour."""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def is_expired(self):
        from django.utils import timezone
        from datetime import timedelta
        return timezone.now() > self.created_at + timedelta(hours=1)

    def __str__(self):
        return f"PasswordResetToken({self.user.username}, used={self.used})"


class AccountSetupToken(models.Model):
    """One-time token for invited account activation. Expires after 24 hours by default."""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='account_setup_tokens')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_account_setup_tokens',
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256((raw_token or '').encode('utf-8')).hexdigest()

    @classmethod
    def issue_for_user(cls, user, created_by=None, hours_valid: int = 24):
        raw_token = secrets.token_urlsafe(32)
        token_obj = cls.objects.create(
            user=user,
            created_by=created_by,
            token_hash=cls.hash_token(raw_token),
            expires_at=timezone.now() + timedelta(hours=max(1, int(hours_valid or 24))),
        )
        return token_obj, raw_token

    @classmethod
    def from_raw_token(cls, raw_token: str):
        if not raw_token:
            return None
        token_hash = cls.hash_token(raw_token)
        return cls.objects.select_related('user').filter(token_hash=token_hash, used=False).first()

    def is_expired(self):
        return timezone.now() > self.expires_at

    def mark_used(self):
        self.used = True
        self.used_at = timezone.now()
        self.save(update_fields=['used', 'used_at'])

    def __str__(self):
        return f"AccountSetupToken({self.user.username}, used={self.used})"


class PersonalAPIToken(models.Model):
    TOKEN_PREFIX = 'hfst_'
    DISPLAY_PREFIX_LENGTH = 18

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='personal_api_tokens',
    )
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=24, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    scopes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256((raw_token or '').encode('utf-8')).hexdigest()

    @classmethod
    def issue_for_user(cls, user, name: str, scopes: list[str], expires_at=None):
        raw_token = f"{cls.TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
        token_obj = cls.objects.create(
            user=user,
            name=(name or '').strip(),
            prefix=raw_token[:cls.DISPLAY_PREFIX_LENGTH],
            token_hash=cls.hash_token(raw_token),
            scopes=[str(scope).strip() for scope in (scopes or []) if str(scope).strip()],
            expires_at=expires_at,
        )
        return token_obj, raw_token

    @classmethod
    def from_raw_token(cls, raw_token: str):
        if not raw_token or not raw_token.startswith(cls.TOKEN_PREFIX):
            return None
        token_hash = cls.hash_token(raw_token)
        return cls.objects.select_related('user').filter(token_hash=token_hash).first()

    def is_expired(self) -> bool:
        return bool(self.expires_at and timezone.now() >= self.expires_at)

    def is_active(self) -> bool:
        return self.revoked_at is None and not self.is_expired()

    def has_scope(self, scope: str) -> bool:
        normalized = (scope or '').strip()
        return normalized in (self.scopes or [])

    def mark_used(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=['last_used_at'])

    def revoke(self):
        if self.revoked_at is not None:
            return
        self.revoked_at = timezone.now()
        self.save(update_fields=['revoked_at'])

    def __str__(self):
        return f"PersonalAPIToken({self.user.username}:{self.name})"


class UserAiCredential(models.Model):
    class Provider(models.TextChoices):
        GEMINI = 'gemini', 'Google Gemini'
        OPENAI = 'openai', 'OpenAI GPT'
        ANTHROPIC = 'anthropic', 'Anthropic Claude'

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='ai_credentials')
    provider = models.CharField(max_length=32, choices=Provider.choices)
    # Store encrypted value; encryption handled in code path, not DB
    encrypted_key = models.TextField()
    key_fingerprint = models.CharField(max_length=64, help_text='SHA-256 hex of the raw key for auditing', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'provider')

    def __str__(self):
        return f"{self.user.username}:{self.provider}"


class AuthProviderSettings(models.Model):
    class AuthMode(models.TextChoices):
        ENTRA_ONLY = 'ENTRA_ONLY', 'Entra only'
        OIDC_ONLY = 'OIDC_ONLY', 'Generic OIDC only'
        ENTRA_AND_OIDC = 'ENTRA_AND_OIDC', 'Entra + Generic OIDC'
        ENTRA_AND_LOCAL_BREAKGLASS = 'ENTRA_AND_LOCAL_BREAKGLASS', 'Entra + Local Break-glass'

    class DefaultLoginProvider(models.TextChoices):
        ENTRA = 'ENTRA', 'Entra'
        OIDC = 'OIDC', 'Generic OIDC'
        LOCAL = 'LOCAL', 'Local'

    singleton_key = models.CharField(max_length=32, unique=True, default='default')
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='auth_settings',
    )
    auth_mode = models.CharField(
        max_length=40,
        choices=AuthMode.choices,
        default=AuthMode.ENTRA_AND_LOCAL_BREAKGLASS,
    )
    default_login_provider = models.CharField(
        max_length=16,
        choices=DefaultLoginProvider.choices,
        default=DefaultLoginProvider.ENTRA,
    )
    enable_entra = models.BooleanField(default=False)
    enable_oidc = models.BooleanField(default=False)
    allow_local_breakglass = models.BooleanField(default=True)
    auto_provision_users = models.BooleanField(default=True)
    sync_claims_on_login = models.BooleanField(default=True)
    enforce_local_mfa = models.BooleanField(default=True)
    breakglass_usernames = models.TextField(
        blank=True,
        default='admin',
        help_text='Comma separated usernames allowed for local emergency login.',
    )

    # Entra provider
    entra_tenant_id = models.CharField(max_length=255, blank=True, default='')
    entra_client_id = models.CharField(max_length=255, blank=True, default='')
    _entra_client_secret = models.TextField(
        db_column='entra_client_secret',
        blank=True,
        default='',
    )
    entra_redirect_uri = models.CharField(max_length=512, blank=True, default='')
    entra_scopes = models.CharField(max_length=512, blank=True, default='openid profile email')
    entra_email_claim = models.CharField(max_length=128, blank=True, default='preferred_username')
    entra_username_claim = models.CharField(max_length=128, blank=True, default='preferred_username')
    entra_role_claim = models.CharField(max_length=128, blank=True, default='roles')

    # Generic OIDC provider
    oidc_issuer_url = models.CharField(max_length=512, blank=True, default='')
    oidc_client_id = models.CharField(max_length=255, blank=True, default='')
    _oidc_client_secret = models.TextField(
        db_column='oidc_client_secret',
        blank=True,
        default='',
    )
    oidc_redirect_uri = models.CharField(max_length=512, blank=True, default='')
    oidc_scopes = models.CharField(max_length=512, blank=True, default='openid profile email')
    oidc_email_claim = models.CharField(max_length=128, blank=True, default='email')
    oidc_username_claim = models.CharField(max_length=128, blank=True, default='preferred_username')
    oidc_role_claim = models.CharField(max_length=128, blank=True, default='roles')
    oidc_verify_ssl = models.BooleanField(
        default=True,
        help_text='Verify TLS certificates for OIDC discovery/token/JWKS requests.',
    )
    oidc_ca_certificate = models.TextField(
        blank=True,
        default='',
        help_text='Optional PEM CA certificate used to verify OIDC TLS.',
    )

    # Role claim mapping
    role_admin_values = models.TextField(blank=True, default='HEF-Admins,Admin,ADMIN')
    role_analyst_values = models.TextField(blank=True, default='HEF-Analysts,Analyst,ANALYST')
    role_reviewer_values = models.TextField(blank=True, default='HEF-Reviewers,Reviewer,REVIEWER')
    default_provisioned_role = models.CharField(
        max_length=24,
        choices=CustomUser.Roles.choices,
        default=CustomUser.Roles.VIEWER,
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Authentication Provider Settings'
        verbose_name_plural = 'Authentication Provider Settings'

    def __str__(self):
        scope = f"org={self.organization_id}" if self.organization_id else "global"
        return f"AuthSettings({scope}, mode={self.auth_mode}, entra={self.enable_entra}, oidc={self.enable_oidc})"

    @property
    def entra_client_secret(self) -> str:
        return _decrypt(self._entra_client_secret)

    @entra_client_secret.setter
    def entra_client_secret(self, value: str):
        self._entra_client_secret = _encrypt(value or '')

    @property
    def oidc_client_secret(self) -> str:
        return _decrypt(self._oidc_client_secret)

    @oidc_client_secret.setter
    def oidc_client_secret(self, value: str):
        self._oidc_client_secret = _encrypt(value or '')

    @property
    def has_entra_client_secret(self) -> bool:
        return bool(self._entra_client_secret)

    @property
    def has_oidc_client_secret(self) -> bool:
        return bool(self._oidc_client_secret)

    @property
    def has_oidc_ca_certificate(self) -> bool:
        return bool((self.oidc_ca_certificate or '').strip())

    @staticmethod
    def _split_csv(text: str | None) -> list[str]:
        raw = (text or '').strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split(',') if part.strip()]

    def breakglass_usernames_list(self) -> list[str]:
        return [value.lower() for value in self._split_csv(self.breakglass_usernames)]

    def role_admin_values_list(self) -> list[str]:
        return self._split_csv(self.role_admin_values)

    def role_analyst_values_list(self) -> list[str]:
        return self._split_csv(self.role_analyst_values)

    def role_reviewer_values_list(self) -> list[str]:
        return self._split_csv(self.role_reviewer_values)

    @classmethod
    def _org_singleton_key(cls, organization) -> str:
        # singleton_key max length is 32; keep org-scoped key deterministic and within limit.
        org_hex = str(getattr(organization, 'id', '')).replace('-', '')
        return f"org:{org_hex[:28]}"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(singleton_key='default', organization=None)
        return obj

    @classmethod
    def get_for_organization(cls, organization):
        if organization is None:
            return cls.get_solo()
        org_key = cls._org_singleton_key(organization)
        obj, _ = cls.objects.get_or_create(
            organization=organization,
            defaults={'singleton_key': org_key},
        )
        if not obj.singleton_key or len(obj.singleton_key) > 32:
            obj.singleton_key = org_key
            obj.save(update_fields=['singleton_key'])
        return obj

    @classmethod
    def resolve_for_user(cls, user):
        org = getattr(user, 'organization', None)
        if org:
            return cls.get_for_organization(org)
        return cls.get_solo()

    @classmethod
    def resolve_for_org_id(cls, organization_id):
        if not organization_id:
            return cls.get_solo()
        org = Organization.objects.filter(pk=organization_id).first()
        if org is None:
            return None
        return cls.get_for_organization(org)


class UserMfaSettings(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='mfa_settings')
    totp_enabled = models.BooleanField(default=False)
    totp_secret_encrypted = models.TextField(blank=True, default='')
    pending_totp_secret_encrypted = models.TextField(blank=True, default='')
    backup_codes_hashes = models.JSONField(default=list, blank=True)
    backup_codes_generated_at = models.DateTimeField(null=True, blank=True)
    failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def totp_secret(self) -> str:
        return _decrypt(self.totp_secret_encrypted)

    @totp_secret.setter
    def totp_secret(self, value: str):
        self.totp_secret_encrypted = _encrypt(value)

    @property
    def pending_totp_secret(self) -> str:
        return _decrypt(self.pending_totp_secret_encrypted)

    @pending_totp_secret.setter
    def pending_totp_secret(self, value: str):
        self.pending_totp_secret_encrypted = _encrypt(value)

    def lock_for_minutes(self, minutes: int = 15):
        self.locked_until = timezone.now() + timedelta(minutes=minutes)

    def is_locked(self) -> bool:
        return bool(self.locked_until and timezone.now() < self.locked_until)

    def hash_backup_code(self, code: str) -> str:
        return hashlib.sha256((code or '').strip().encode('utf-8')).hexdigest()

    def verify_and_consume_backup_code(self, code: str) -> bool:
        normalized = (code or '').strip()
        if not normalized:
            return False
        hashed = self.hash_backup_code(normalized)
        if hashed in self.backup_codes_hashes:
            codes = list(self.backup_codes_hashes or [])
            codes.remove(hashed)
            self.backup_codes_hashes = codes
            return True
        return False

    def __str__(self):
        return f"MFA({self.user.username}, enabled={self.totp_enabled})"


def _default_mfa_challenge_id():
    return secrets.token_urlsafe(24)


class MfaLoginChallenge(models.Model):
    challenge_id = models.CharField(max_length=64, unique=True, default=_default_mfa_challenge_id)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='mfa_login_challenges')
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    failed_attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def create_for_user(cls, user, minutes_valid: int = 5):
        return cls.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(minutes=minutes_valid),
        )

    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"MFAChallenge({self.user.username}, used={self.used})"


class MfaAuditEvent(models.Model):
    class Event(models.TextChoices):
        TOTP_ENROLL_STARTED = 'TOTP_ENROLL_STARTED', 'TOTP enroll started'
        TOTP_ENROLL_CONFIRMED = 'TOTP_ENROLL_CONFIRMED', 'TOTP enroll confirmed'
        TOTP_DISABLED = 'TOTP_DISABLED', 'TOTP disabled'
        BACKUP_CODES_REGENERATED = 'BACKUP_CODES_REGENERATED', 'Backup codes regenerated'
        LOGIN_CHALLENGE_CREATED = 'LOGIN_CHALLENGE_CREATED', 'MFA login challenge created'
        LOGIN_SUCCESS = 'LOGIN_SUCCESS', 'MFA login success'
        LOGIN_FAILED = 'LOGIN_FAILED', 'MFA login failed'
        LOGIN_LOCKED = 'LOGIN_LOCKED', 'MFA locked'
        ADMIN_RESET = 'ADMIN_RESET', 'Admin reset MFA'

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='mfa_audit_events')
    event = models.CharField(max_length=64, choices=Event.choices)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"MfaAuditEvent({self.user.username}, {self.event})"


class WebAuthnCredential(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='webauthn_credentials')
    name = models.CharField(max_length=128, blank=True, default='')
    credential_id = models.TextField(unique=True)
    public_key = models.TextField()
    sign_count = models.PositiveIntegerField(default=0)
    transports = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"WebAuthnCredential({self.user.username}, {self.name or 'security-key'})"


class WebAuthnChallenge(models.Model):
    class ChallengeType(models.TextChoices):
        REGISTRATION = 'REGISTRATION', 'Registration'
        AUTHENTICATION = 'AUTHENTICATION', 'Authentication'
        PASSWORDLESS = 'PASSWORDLESS', 'Passwordless'

    challenge_id = models.CharField(max_length=64, unique=True, default=_default_mfa_challenge_id)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='webauthn_challenges', null=True, blank=True)
    username = models.CharField(max_length=150, blank=True, default='')
    challenge_type = models.CharField(max_length=16, choices=ChallengeType.choices)
    challenge = models.TextField()
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def create_challenge(cls, challenge_type: str, challenge: str, user=None, username: str = '', minutes_valid: int = 5):
        return cls.objects.create(
            challenge_type=challenge_type,
            challenge=challenge,
            user=user,
            username=username or '',
            expires_at=timezone.now() + timedelta(minutes=minutes_valid),
        )

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"WebAuthnChallenge({self.challenge_type}, used={self.used})"
