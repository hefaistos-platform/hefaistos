import uuid
from dataclasses import dataclass
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from cryptography.fernet import Fernet, InvalidToken

MISP_INSTANCE_LIMIT = 5
SHARING_SCOPE_CHOICES = [
    ('WORKBENCH', 'Workbench'),
    ('RULES', 'Rules'),
    ('ACH', 'ACH'),
    ('ADVOPS', 'ADVOPS'),
    ('ALL', 'All'),
]
SHARING_SCOPE_VALUES = {choice[0] for choice in SHARING_SCOPE_CHOICES}
HEFAISTOS_AUTO_PULL_SCHEDULE_CHOICES = [
    ('DAILY', 'Daily'),
    ('WEEKLY', 'Weekly'),
]
HEFAISTOS_AUTO_PULL_SCHEDULE_VALUES = {choice[0] for choice in HEFAISTOS_AUTO_PULL_SCHEDULE_CHOICES}

# ---------------------------------------------------------------------------
# Field-level encryption helpers (same pattern as rules/models.py)
# ---------------------------------------------------------------------------
try:
    _FERNET = Fernet(settings.FIELD_ENCRYPTION_KEY)
except Exception:
    _FERNET = None


def _encrypt(text: str) -> str | None:
    if not _FERNET or not text:
        return None
    return _FERNET.encrypt(text.encode()).decode()


def _decrypt(encrypted_text: str) -> str | None:
    if not _FERNET or not encrypted_text:
        return None
    try:
        return _FERNET.decrypt(encrypted_text.encode()).decode()
    except InvalidToken:
        return None


class Entity(models.Model):
    """Top-level holding company / MSSP that owns organizations."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Entities"

    def __str__(self):
        return self.name


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    max_users = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Maximum users allowed in this organization. Leave empty for unlimited.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Link to parent Entity (nullable so existing orgs are valid)
    entity = models.ForeignKey(
        Entity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organizations",
    )
    workbench_visibility_policy = models.JSONField(
        default=dict,
        blank=True,
        help_text="Organization-level workbench visibility policy overrides.",
    )

    def __str__(self):
        return self.name

    def current_member_count(self) -> int:
        return self.customuser_set.count()

    def has_user_capacity(self, incoming_users: int = 1) -> bool:
        if self.max_users is None:
            return True
        return (self.current_member_count() + max(0, int(incoming_users or 0))) <= self.max_users

    def clean(self):
        super().clean()
        if self.max_users is None:
            return
        current_members = self.current_member_count() if self.pk else 0
        if self.max_users < current_members:
            raise ValidationError(
                {"max_users": f"Cannot set max users below current member count ({current_members})."}
            )


class OrganizationBillingProfile(models.Model):
    """Stripe-backed billing state and capacity entitlements for an organization."""

    BASE_USERS = 1
    BASE_ORGANIZATIONS = 1
    BASE_YEARLY_EUR = 240
    EXTRA_USER_YEARLY_EUR = 120
    EXTRA_ORG_YEARLY_EUR = 10

    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name='billing_profile',
    )
    stripe_customer_id = models.CharField(max_length=120, blank=True, default='')
    stripe_subscription_id = models.CharField(max_length=120, blank=True, default='')

    included_users = models.PositiveIntegerField(default=BASE_USERS)
    included_organizations = models.PositiveIntegerField(default=BASE_ORGANIZATIONS)
    extra_users = models.PositiveIntegerField(default=0)
    extra_organizations = models.PositiveIntegerField(default=0)

    currency = models.CharField(max_length=8, default='EUR')
    last_checkout_session_id = models.CharField(max_length=120, blank=True, default='')
    last_payment_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Organization Billing Profile'
        verbose_name_plural = 'Organization Billing Profiles'

    def __str__(self):
        return f"BillingProfile({self.organization.name})"

    @property
    def max_users(self) -> int:
        return int(self.included_users) + int(self.extra_users)

    @property
    def max_organizations(self) -> int:
        return int(self.included_organizations) + int(self.extra_organizations)

    def has_organization_capacity(self, incoming_organizations: int = 1) -> bool:
        total = int(incoming_organizations or 0)
        if total < 0:
            total = 0
        # Organization count is scoped to the same parent entity when available.
        if self.organization.entity_id:
            current_count = Organization.objects.filter(entity_id=self.organization.entity_id).count()
        else:
            current_count = 1
        return (current_count + total) <= self.max_organizations


class OrganizationManagerAccess(models.Model):
    """Additional organizations a user can manage without changing their primary org context."""

    class AccessRole(models.TextChoices):
        OWNER = 'OWNER', 'Owner'
        RESOURCE_MANAGER = 'RESOURCE_MANAGER', 'Resource Manager'

    user = models.ForeignKey(
        'identity.CustomUser',
        on_delete=models.CASCADE,
        related_name='managed_organization_access',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='manager_access',
    )
    access_role = models.CharField(
        max_length=32,
        choices=AccessRole.choices,
        default=AccessRole.RESOURCE_MANAGER,
    )
    created_by = models.ForeignKey(
        'identity.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_organization_manager_access',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'organization')]
        verbose_name = 'Organization Manager Access'
        verbose_name_plural = 'Organization Manager Access'

    def __str__(self):
        return f"OrgManagerAccess({self.user.username} -> {self.organization.name}, {self.access_role})"


class MISPInstance(models.Model):
    """A MISP instance configured for an organization (max 5 per org)."""

    AUTO_PULL_SCHEDULE_CHOICES = [
        ('HOURLY', 'Hourly'),
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="misp_instances",
    )
    name = models.CharField(max_length=255)
    url = models.CharField(max_length=512)
    auth_key = models.TextField()
    verify_ssl = models.BooleanField(default=True)
    auto_pull_enabled = models.BooleanField(
        default=False,
        help_text='Enable scheduled automatic Waiting Room import from this MISP instance.',
    )
    auto_pull_schedule = models.CharField(
        max_length=16,
        choices=AUTO_PULL_SCHEDULE_CHOICES,
        default='DAILY',
        help_text='Automatic import frequency when auto_pull_enabled is on.',
    )
    auto_pull_tag = models.CharField(
        max_length=255,
        blank=True,
        default='HEFAISTOS',
        help_text='Only import events carrying this tag during scheduled auto-pull. Empty means import all events.',
    )
    next_auto_pull_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Next scheduled automatic import time.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        unique_together = [("organization", "name")]

    def __str__(self):
        return f"{self.name} ({self.organization.name})"


class PlatformCredential(models.Model):
    """Encrypted API credentials for a SIEM/EDR deployment platform."""

    PLATFORM_CHOICES = [
        ('defender', 'Microsoft Defender'),
        ('sentinel', 'Azure Sentinel'),
        ('splunk', 'Splunk'),
        ('qradar', 'IBM QRadar'),
        ('wazuh', 'Wazuh'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='platform_credentials',
    )
    platform = models.CharField(max_length=50, choices=PLATFORM_CHOICES)
    profile_name = models.CharField(
        max_length=100,
        default='default',
        help_text='Credential profile name (for example: default, prod-eu, soc-lab).',
    )
    is_default = models.BooleanField(
        default=False,
        help_text='When enabled, this profile is preferred for deployments when no profile is explicitly selected.',
    )
    # Credential fields – all stored encrypted
    _credentials_json = models.TextField(
        db_column='credentials_json',
        help_text='Encrypted JSON blob of platform credentials (do not access directly)',
        blank=True,
        default='',
    )
    enabled = models.BooleanField(default=True)

    # Connection test metadata
    last_tested = models.DateTimeField(null=True, blank=True)
    test_status = models.BooleanField(null=True, blank=True)
    test_message = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'identity.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_platform_credentials',
    )

    class Meta:
        unique_together = [('organization', 'platform', 'profile_name')]
        verbose_name = "Platform Credential"
        verbose_name_plural = "Platform Credentials"
        ordering = ['platform', 'profile_name']

    def __str__(self):
        return f"{self.get_platform_display()} [{self.profile_name}] credentials ({self.organization.name})"

    @property
    def credentials(self) -> dict:
        """Return decrypted credentials dict."""
        raw = _decrypt(self._credentials_json)
        if not raw:
            return {}
        import json
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {}

    @credentials.setter
    def credentials(self, value: dict) -> None:
        """Encrypt and store the credentials dict."""
        import json
        self._credentials_json = _encrypt(json.dumps(value)) or ''

    def set_credentials(self, credentials_dict: dict) -> None:
        """Encrypt and store credentials dict (alias for property setter)."""
        self.credentials = credentials_dict

    def get_credentials(self) -> dict:
        """Decrypt and return credentials dict (alias for property getter)."""
        return self.credentials

    @classmethod
    def get_preferred_for_platform(cls, organization, platform: str, profile_name: str | None = None):
        """Return the preferred enabled credential row for an org+platform.

        Selection order:
        1) exact enabled profile match (when profile_name provided)
        2) enabled default profile (is_default=True)
        3) enabled profile named "default"
        4) first enabled profile by deterministic ordering
        """
        qs = cls.objects.filter(
            organization=organization,
            platform=str(platform or '').strip().lower(),
            enabled=True,
        )
        if not qs.exists():
            return None

        if profile_name:
            exact = qs.filter(profile_name=str(profile_name).strip()).first()
            if exact:
                return exact

        preferred = qs.filter(is_default=True).first()
        if preferred:
            return preferred

        default_named = qs.filter(profile_name='default').first()
        if default_named:
            return default_named

        return qs.first()

    @classmethod
    def preferred_credentials_map(
        cls,
        organization,
        platforms: list[str],
        profile_overrides: dict[str, str] | None = None,
    ) -> dict[str, dict]:
        """Resolve one enabled credential dict per platform.

        Args:
            organization: Organization instance.
            platforms: list of platform keys, for example ['defender', 'sentinel'].
            profile_overrides: optional platform->profile_name mapping.
        """
        resolved: dict[str, dict] = {}
        profile_overrides = profile_overrides or {}
        for platform in platforms or []:
            normalized = str(platform or '').strip().lower()
            if not normalized or normalized in resolved:
                continue
            row = cls.get_preferred_for_platform(
                organization=organization,
                platform=normalized,
                profile_name=profile_overrides.get(normalized),
            )
            if row:
                resolved[normalized] = row.credentials
        return resolved

    def test_connection(self) -> tuple[bool, str]:
        """
        Test platform connectivity using stored credentials.

        Returns:
            (success: bool, message: str)
        """
        import logging
        from django.utils import timezone
        from rules.deployers import PLATFORM_DEPLOYER_MAP

        logger = logging.getLogger(__name__)

        try:
            creds = self.get_credentials()
            if not creds:
                return False, "No credentials configured"

            deployer_class = PLATFORM_DEPLOYER_MAP.get(self.platform)
            if not deployer_class:
                return False, f"Unknown platform: {self.platform}"

            deployer = deployer_class(creds)
            valid, error = deployer.validate_credentials()
            if not valid:
                success, msg = False, f"Credential validation failed: {error}"
            else:
                try:
                    authenticated = deployer.authenticate()
                    success = bool(authenticated)
                    msg = "Connection successful" if success else "Authentication failed"
                except Exception as exc:
                    success, msg = False, str(exc)

            self.last_tested = timezone.now()
            self.test_status = success
            self.test_message = msg
            self.save(update_fields=['last_tested', 'test_status', 'test_message'])

            return success, msg

        except Exception as exc:
            logger.error("Connection test failed for %s: %s", self.platform, exc)
            return False, str(exc)


class SmtpSettings(models.Model):
    """Singleton SMTP settings used by email service (overrides Mailgun when configured)."""

    class Encryption(models.TextChoices):
        NONE = 'NONE', 'None'
        SSL = 'SSL', 'SSL'
        STARTTLS = 'STARTTLS', 'STARTTLS'

    class LoginMethod(models.TextChoices):
        PLAIN = 'PLAIN', 'PLAIN'
        LOGIN = 'LOGIN', 'LOGIN'

    singleton_key = models.CharField(max_length=32, unique=True, default='default')
    smtp_server = models.CharField(max_length=255)
    smtp_port = models.PositiveIntegerField(default=587)
    encryption = models.CharField(max_length=16, choices=Encryption.choices, default=Encryption.STARTTLS)
    login_method = models.CharField(max_length=16, choices=LoginMethod.choices, default=LoginMethod.PLAIN)
    smtp_username = models.CharField(max_length=255, blank=True, default='')
    _smtp_password = models.TextField(
        db_column='smtp_password',
        help_text='Encrypted SMTP password (do not access directly)',
        blank=True,
        default='',
    )
    from_email = models.EmailField(blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'SMTP Settings'
        verbose_name_plural = 'SMTP Settings'

    def __str__(self):
        return f"SMTP({self.smtp_server}:{self.smtp_port}, {self.encryption}, {self.login_method})"

    @property
    def smtp_password(self) -> str:
        return _decrypt(self._smtp_password) or ''

    @smtp_password.setter
    def smtp_password(self, value: str) -> None:
        self._smtp_password = _encrypt(value or '') or ''

    @property
    def has_password(self) -> bool:
        return bool(self._smtp_password)

    def clean(self):
        errors = {}

        if not (self.smtp_server or '').strip():
            errors['smtp_server'] = 'This field cannot be blank.'

        if not (1 <= int(self.smtp_port or 0) <= 65535):
            errors['smtp_port'] = 'Port must be between 1 and 65535.'

        if self.login_method == self.LoginMethod.LOGIN:
            if not (self.smtp_username or '').strip():
                errors['smtp_username'] = 'Username is required when login method is LOGIN.'
            if not self.has_password:
                errors['smtp_password'] = 'Password is required when login method is LOGIN.'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


@dataclass
class EffectiveSmtpConfig:
    smtp_server: str
    smtp_port: int
    encryption: str
    login_method: str
    smtp_username: str
    smtp_password: str
    has_password: bool
    from_email: str
    updated_at: object | None
    source: str
    shared_profile_id: uuid.UUID | None = None
    shared_profile_name: str = ''
    enforce_shared: bool = False
    custom_configured: bool = False
    organization_id: uuid.UUID | None = None


class SharedSmtpProfile(models.Model):
    """System-wide SMTP profile managed by platform superusers."""

    class Encryption(models.TextChoices):
        NONE = 'NONE', 'None'
        SSL = 'SSL', 'SSL'
        STARTTLS = 'STARTTLS', 'STARTTLS'

    class LoginMethod(models.TextChoices):
        PLAIN = 'PLAIN', 'PLAIN'
        LOGIN = 'LOGIN', 'LOGIN'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    smtp_server = models.CharField(max_length=255)
    smtp_port = models.PositiveIntegerField(default=587)
    encryption = models.CharField(max_length=16, choices=Encryption.choices, default=Encryption.STARTTLS)
    login_method = models.CharField(max_length=16, choices=LoginMethod.choices, default=LoginMethod.PLAIN)
    smtp_username = models.CharField(max_length=255, blank=True, default='')
    _smtp_password = models.TextField(
        db_column='smtp_password',
        help_text='Encrypted SMTP password (do not access directly)',
        blank=True,
        default='',
    )
    from_email = models.EmailField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'identity.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_shared_smtp_profiles',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Shared SMTP Profile'
        verbose_name_plural = 'Shared SMTP Profiles'

    def __str__(self):
        return f"SharedSMTP({self.name})"

    @property
    def smtp_password(self) -> str:
        return _decrypt(self._smtp_password) or ''

    @smtp_password.setter
    def smtp_password(self, value: str) -> None:
        self._smtp_password = _encrypt(value or '') or ''

    @property
    def has_password(self) -> bool:
        return bool(self._smtp_password)

    def clean(self):
        errors = {}

        if not (self.name or '').strip():
            errors['name'] = 'This field cannot be blank.'
        if not (self.smtp_server or '').strip():
            errors['smtp_server'] = 'This field cannot be blank.'
        if not (1 <= int(self.smtp_port or 0) <= 65535):
            errors['smtp_port'] = 'Port must be between 1 and 65535.'

        if self.login_method == self.LoginMethod.LOGIN:
            if not (self.smtp_username or '').strip():
                errors['smtp_username'] = 'Username is required when login method is LOGIN.'
            if not self.has_password:
                errors['smtp_password'] = 'Password is required when login method is LOGIN.'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class OrganizationSmtpSettings(models.Model):
    """Per-organization SMTP policy and optional custom SMTP override."""

    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name='smtp_settings',
    )
    shared_profile = models.ForeignKey(
        SharedSmtpProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='organization_assignments',
    )
    enforce_shared = models.BooleanField(
        default=False,
        help_text='When enabled, organization admins cannot override with custom SMTP.',
    )
    custom_enabled = models.BooleanField(
        default=False,
        help_text='Enable organization-local SMTP configuration.',
    )
    custom_smtp_server = models.CharField(max_length=255, blank=True, default='')
    custom_smtp_port = models.PositiveIntegerField(default=587)
    custom_encryption = models.CharField(
        max_length=16,
        choices=SharedSmtpProfile.Encryption.choices,
        default=SharedSmtpProfile.Encryption.STARTTLS,
    )
    custom_login_method = models.CharField(
        max_length=16,
        choices=SharedSmtpProfile.LoginMethod.choices,
        default=SharedSmtpProfile.LoginMethod.PLAIN,
    )
    custom_smtp_username = models.CharField(max_length=255, blank=True, default='')
    _custom_smtp_password = models.TextField(
        db_column='custom_smtp_password',
        help_text='Encrypted custom SMTP password (do not access directly)',
        blank=True,
        default='',
    )
    custom_from_email = models.EmailField(blank=True, default='')
    updated_by = models.ForeignKey(
        'identity.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_org_smtp_settings',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Organization SMTP Settings'
        verbose_name_plural = 'Organization SMTP Settings'

    def __str__(self):
        return f"OrgSMTP({self.organization.name})"

    @property
    def custom_smtp_password(self) -> str:
        return _decrypt(self._custom_smtp_password) or ''

    @custom_smtp_password.setter
    def custom_smtp_password(self, value: str) -> None:
        self._custom_smtp_password = _encrypt(value or '') or ''

    @property
    def has_custom_password(self) -> bool:
        return bool(self._custom_smtp_password)

    @property
    def has_custom_config(self) -> bool:
        return bool(self.custom_enabled and (self.custom_smtp_server or '').strip())

    def clean(self):
        errors = {}
        if self.enforce_shared and not self.shared_profile_id:
            errors['shared_profile'] = 'Shared profile is required when enforce_shared is enabled.'

        if self.custom_enabled:
            if not (self.custom_smtp_server or '').strip():
                errors['custom_smtp_server'] = 'SMTP server is required when custom SMTP is enabled.'
            if not (1 <= int(self.custom_smtp_port or 0) <= 65535):
                errors['custom_smtp_port'] = 'Port must be between 1 and 65535.'
            if self.custom_login_method == SharedSmtpProfile.LoginMethod.LOGIN:
                if not (self.custom_smtp_username or '').strip():
                    errors['custom_smtp_username'] = 'Username is required when login method is LOGIN.'
                if not self.has_custom_password:
                    errors['custom_smtp_password'] = 'Password is required when login method is LOGIN.'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def _config_from_shared(self, source: str) -> EffectiveSmtpConfig | None:
        profile = self.shared_profile
        if not profile or not profile.is_active:
            return None
        return EffectiveSmtpConfig(
            smtp_server=profile.smtp_server or '',
            smtp_port=int(profile.smtp_port or 0),
            encryption=profile.encryption or SharedSmtpProfile.Encryption.NONE,
            login_method=profile.login_method or SharedSmtpProfile.LoginMethod.PLAIN,
            smtp_username=profile.smtp_username or '',
            smtp_password=profile.smtp_password or '',
            has_password=profile.has_password,
            from_email=profile.from_email or '',
            updated_at=profile.updated_at,
            source=source,
            shared_profile_id=profile.id,
            shared_profile_name=profile.name,
            enforce_shared=bool(self.enforce_shared),
            custom_configured=self.has_custom_config,
            organization_id=self.organization_id,
        )

    def _config_from_custom(self) -> EffectiveSmtpConfig:
        return EffectiveSmtpConfig(
            smtp_server=self.custom_smtp_server or '',
            smtp_port=int(self.custom_smtp_port or 0),
            encryption=self.custom_encryption or SharedSmtpProfile.Encryption.NONE,
            login_method=self.custom_login_method or SharedSmtpProfile.LoginMethod.PLAIN,
            smtp_username=self.custom_smtp_username or '',
            smtp_password=self.custom_smtp_password or '',
            has_password=self.has_custom_password,
            from_email=self.custom_from_email or '',
            updated_at=self.updated_at,
            source='CUSTOM',
            shared_profile_id=self.shared_profile_id,
            shared_profile_name=self.shared_profile.name if self.shared_profile_id else '',
            enforce_shared=bool(self.enforce_shared),
            custom_configured=self.has_custom_config,
            organization_id=self.organization_id,
        )

    def get_effective_config(self) -> EffectiveSmtpConfig | None:
        if self.shared_profile_id and self.enforce_shared:
            cfg = self._config_from_shared('SHARED_LOCKED')
            if cfg is not None:
                return cfg
        if self.has_custom_config:
            return self._config_from_custom()
        if self.shared_profile_id:
            cfg = self._config_from_shared('SHARED')
            if cfg is not None:
                return cfg
        return _legacy_global_smtp_config(organization_id=self.organization_id)


def _legacy_global_smtp_config(organization_id=None) -> EffectiveSmtpConfig | None:
    legacy = SmtpSettings.objects.filter(singleton_key='default').first()
    if legacy is None:
        return None
    return EffectiveSmtpConfig(
        smtp_server=legacy.smtp_server or '',
        smtp_port=int(legacy.smtp_port or 0),
        encryption=legacy.encryption or SharedSmtpProfile.Encryption.NONE,
        login_method=legacy.login_method or SharedSmtpProfile.LoginMethod.PLAIN,
        smtp_username=legacy.smtp_username or '',
        smtp_password=legacy.smtp_password or '',
        has_password=legacy.has_password,
        from_email=legacy.from_email or '',
        updated_at=legacy.updated_at,
        source='LEGACY_GLOBAL',
        organization_id=organization_id,
    )


def get_effective_smtp_for_organization(organization, create_if_missing: bool = True) -> EffectiveSmtpConfig | None:
    if organization is None:
        return _legacy_global_smtp_config()

    settings_obj = OrganizationSmtpSettings.objects.select_related('shared_profile').filter(
        organization=organization
    ).first()
    if settings_obj is None and create_if_missing:
        settings_obj = OrganizationSmtpSettings.objects.create(organization=organization)
    if settings_obj is None:
        return _legacy_global_smtp_config(organization_id=getattr(organization, 'id', None))
    return settings_obj.get_effective_config()


class OrganizationAITaskConfig(models.Model):
    """Per-organization configuration for scheduled AI-assisted operational tasks."""

    class Schedule(models.TextChoices):
        DAILY = 'DAILY', 'Daily'
        WEEKLY = 'WEEKLY', 'Weekly'
        MONTHLY = 'MONTHLY', 'Monthly'

    class LastStatus(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'
        SKIPPED = 'SKIPPED', 'Skipped'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='ai_task_configs',
    )
    task_key = models.CharField(max_length=64)
    enabled = models.BooleanField(default=False)

    schedule = models.CharField(
        max_length=16,
        choices=Schedule.choices,
        default=Schedule.WEEKLY,
    )
    day_of_week = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        help_text='For WEEKLY schedules: 0=Monday ... 6=Sunday.',
    )
    day_of_month = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(28)],
        help_text='For MONTHLY schedules: day 1-28.',
    )
    run_hour = models.PositiveSmallIntegerField(
        default=8,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
    )
    run_minute = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(59)],
    )

    next_run_at = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(
        max_length=16,
        choices=LastStatus.choices,
        blank=True,
        null=True,
    )
    last_message = models.TextField(blank=True, default='')

    updated_by = models.ForeignKey(
        'identity.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_org_ai_task_configs',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['task_key']
        unique_together = [('organization', 'task_key')]
        verbose_name = 'Organization AI Task Configuration'
        verbose_name_plural = 'Organization AI Task Configurations'

    def __str__(self):
        return f'AITaskConfig({self.organization.name}, {self.task_key}, enabled={self.enabled})'


class OrganizationAITaskRun(models.Model):
    """Execution log for organization AI-assisted operational tasks."""

    class Status(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'
        SKIPPED = 'SKIPPED', 'Skipped'

    class Trigger(models.TextChoices):
        SCHEDULED = 'SCHEDULED', 'Scheduled'
        MANUAL = 'MANUAL', 'Manual'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='ai_task_runs',
    )
    task_config = models.ForeignKey(
        OrganizationAITaskConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='runs',
    )
    task_key = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices)
    trigger = models.CharField(
        max_length=16,
        choices=Trigger.choices,
        default=Trigger.SCHEDULED,
    )

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    run_by = models.ForeignKey(
        'identity.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='org_ai_task_runs',
    )

    output_summary = models.TextField(blank=True, default='')
    error_message = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['organization', 'task_key']),
            models.Index(fields=['organization', 'started_at']),
        ]
        verbose_name = 'Organization AI Task Run'
        verbose_name_plural = 'Organization AI Task Runs'

    def __str__(self):
        return f'AITaskRun({self.organization.name}, {self.task_key}, {self.status})'


class OpenTidePublishProfile(models.Model):
    """Reusable HEF publish configuration linking a repository to deployment targets."""
    class KqlTargetPolicy(models.TextChoices):
        DEFENDER = 'defender', 'Defender'
        SENTINEL = 'sentinel', 'Sentinel'
        BOTH = 'both', 'Defender + Sentinel'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='opentide_publish_profiles',
    )
    repository = models.ForeignKey(
        'rules.RuleRepository',
        on_delete=models.CASCADE,
        related_name='opentide_publish_profiles',
    )
    name = models.CharField(max_length=100)
    branch = models.CharField(max_length=255, default='main')
    target_folder = models.CharField(max_length=255, blank=True, default='')
    push_platform_rules = models.BooleanField(
        default=False,
        help_text='When enabled, also push individual platform rule files (kql/, splunk/, sigma/, etc.) alongside the OpenTide bundle.',
    )
    enabled_platforms = models.JSONField(
        default=list,
        blank=True,
        help_text='Default deployment platforms for HEF publish jobs.',
    )
    use_graph_configured_platforms = models.BooleanField(
        default=True,
        help_text='Use workbench configured_platforms when no explicit platforms are set on the profile.',
    )
    kql_target_policy = models.CharField(
        max_length=16,
        choices=KqlTargetPolicy.choices,
        default=KqlTargetPolicy.DEFENDER,
        help_text="Default target mapping for 'kql' platform values: defender, sentinel, or both.",
    )
    enabled = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'identity.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_opentide_publish_profiles',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = [('organization', 'name')]
        verbose_name = 'OpenTIDE HEF Publish Profile'
        verbose_name_plural = 'OpenTIDE HEF Publish Profiles'

    def __str__(self):
        return f'{self.name} ({self.organization.name})'


class DacDeploymentConfig(models.Model):
    """Organisation-level automation settings for DEPLOYED workbench transitions."""

    class Mode(models.TextChoices):
        NONE = 'NONE', 'Do nothing'
        GIT_PUSH = 'GIT_PUSH', 'Generate and push to GitHub'
        GIT_PUSH_AND_DEPLOY = 'GIT_PUSH_AND_DEPLOY', 'Generate, push, and deploy'
        DEPLOY_ONLY = 'DEPLOY_ONLY', 'Just push rule to target platform'

    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name='dac_deployment_config',
    )
    mode = models.CharField(max_length=32, choices=Mode.choices, default=Mode.NONE)
    target_repository = models.ForeignKey(
        'rules.RuleRepository',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dac_deployment_configs',
    )
    target_branch = models.CharField(max_length=255, default='main')
    target_folder = models.CharField(max_length=255, blank=True, default='')
    target_platforms = models.JSONField(default=list, blank=True)
    publish_profile = models.ForeignKey(
        OpenTidePublishProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dac_deployment_configs',
    )
    updated_by = models.ForeignKey(
        'identity.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_dac_deployment_configs',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'DaC Deployment Configuration'
        verbose_name_plural = 'DaC Deployment Configurations'

    def __str__(self):
        return f'DaCConfig({self.organization.name}, mode={self.mode})'


class OpenTideHefPublishJob(models.Model):
    """Tracks asynchronous OpenTIDE HEF publish jobs processed via RabbitMQ."""

    STATUS_CHOICES = [
        ('QUEUED', 'Queued'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    SOURCE_CHOICES = [
        ('MANUAL', 'Manual'),
        ('DAC_AUTOMATION', 'DaC Automation'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    playbook = models.ForeignKey(
        'playbooks.PlaybookGraph',
        on_delete=models.CASCADE,
        related_name='hef_publish_jobs',
    )
    user = models.ForeignKey(
        'identity.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='opentide_hef_publish_jobs',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='hef_publish_jobs',
    )
    profile = models.ForeignKey(
        OpenTidePublishProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='publish_jobs',
    )
    repository = models.ForeignKey(
        'rules.RuleRepository',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hef_publish_jobs',
    )
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='MANUAL')
    source_graph_version = models.IntegerField(null=True, blank=True)
    source_graph_minor_version = models.IntegerField(null=True, blank=True)
    rule = models.ForeignKey(
        'rules.DetectionRule',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hef_publish_jobs',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='QUEUED')
    progress = models.TextField(blank=True, default='')
    commit_message = models.TextField(blank=True, default='')
    branch = models.CharField(max_length=255, default='main')
    target_folder = models.CharField(max_length=255, blank=True, default='')
    push_opentide_bundle = models.BooleanField(default=True)
    push_platform_rules = models.BooleanField(default=False)
    requested_platforms = models.JSONField(default=list, blank=True)
    deployed_platforms = models.JSONField(default=list, blank=True)
    deployment_results = models.JSONField(default=list, blank=True)
    failure_summary = models.JSONField(default=dict, blank=True)
    commit_sha = models.CharField(max_length=40, blank=True, default='')
    github_url = models.CharField(max_length=1024, blank=True, default='')
    file_paths = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'OpenTIDE HEF Publish Job'
        verbose_name_plural = 'OpenTIDE HEF Publish Jobs'

    def __str__(self):
        return f'HEFPublishJob({self.id}) [{self.status}] – {self.playbook}'


class OpenTideHefImportJob(models.Model):
    """Tracks asynchronous OpenTIDE HEF import jobs processed via RabbitMQ."""

    STATUS_CHOICES = [
        ('QUEUED', 'Queued'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    CONFLICT_MODE_CHOICES = [
        ('NEW_COPY', 'Create new copy'),
        ('OVERWRITE', 'Overwrite existing by MDR UUID'),
        ('SKIP', 'Skip if UUID already exists'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'identity.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='opentide_hef_import_jobs',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='hef_import_jobs',
    )
    profile = models.ForeignKey(
        OpenTidePublishProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='import_jobs',
    )
    # Manual source (when no profile is selected)
    repo_owner = models.CharField(max_length=255, blank=True, default='')
    repo_name = models.CharField(max_length=255, blank=True, default='')
    branch = models.CharField(max_length=255, default='main')
    target_folder = models.CharField(max_length=255, blank=True, default='')
    source_commit_sha = models.CharField(max_length=40, blank=True, default='')

    # Job parameters
    selected_bundles = models.JSONField(
        default=list,
        blank=True,
        help_text='List of bundle paths selected for import',
    )
    conflict_mode = models.CharField(
        max_length=20,
        choices=CONFLICT_MODE_CHOICES,
        default='NEW_COPY',
    )
    import_platform_rules = models.BooleanField(default=True)
    dry_run = models.BooleanField(default=False)

    # Job state
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='QUEUED')
    progress = models.TextField(blank=True, default='')
    results = models.JSONField(
        default=list,
        blank=True,
        help_text='Per-bundle import results [{bundle_path, workbench_id, status, errors}]',
    )
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'OpenTIDE HEF Import Job'
        verbose_name_plural = 'OpenTIDE HEF Import Jobs'

    def __str__(self):
        return f'HEFImportJob({self.id}) [{self.status}]'


class HefaistosInstanceIdentity(models.Model):
    """Organization-scoped HEFAISTOS sharing identity (UUID v5)."""

    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name='hefaistos_instance_identity',
        null=True,
        blank=True,
    )
    singleton_key = models.CharField(max_length=64, blank=True, default='', db_index=True)
    instance_id = models.UUIDField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'HEFAISTOS Instance Identity'
        verbose_name_plural = 'HEFAISTOS Instance Identities'

    def __str__(self):
        if self.organization_id:
            return f'InstanceIdentity({self.organization.name}: {self.instance_id})'
        return f'InstanceIdentity(global: {self.instance_id})'


class HefaistosRemotePeer(models.Model):
    """Configured remote HEFAISTOS peer used for PULL-only synchronization."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='hefaistos_remote_peers',
    )
    name = models.CharField(max_length=120)
    remote_url = models.URLField(max_length=512)
    remote_instance_id = models.UUIDField()
    _api_key = models.TextField(
        db_column='api_key',
        blank=True,
        default='',
        help_text='Encrypted API key for remote pull authentication.',
    )
    default_scope = models.CharField(
        max_length=16,
        choices=SHARING_SCOPE_CHOICES,
        default='ALL',
        help_text='Default content range to pull from the remote instance.',
    )
    auto_pull_enabled = models.BooleanField(
        default=False,
        help_text='Enable scheduled automatic PULL from this remote peer.',
    )
    auto_pull_schedule = models.CharField(
        max_length=16,
        choices=HEFAISTOS_AUTO_PULL_SCHEDULE_CHOICES,
        default='DAILY',
        help_text='Automatic PULL frequency when auto_pull_enabled is on.',
    )
    next_auto_pull_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Next scheduled automatic PULL time.',
    )
    verify_ssl = models.BooleanField(default=True)
    allow_self_signed = models.BooleanField(default=False)
    tls_cert_fingerprint = models.CharField(
        max_length=128,
        blank=True,
        default='',
        help_text='Optional SHA-256 TLS certificate fingerprint pin (hex).',
    )
    enabled = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=16, blank=True, default='')
    last_sync_message = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        'identity.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_hefaistos_remote_peers',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = [('organization', 'name')]
        verbose_name = 'HEFAISTOS Remote Peer'
        verbose_name_plural = 'HEFAISTOS Remote Peers'

    def __str__(self):
        return f'{self.name} ({self.organization.name})'

    @property
    def api_key(self) -> str:
        return _decrypt(self._api_key) or ''

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._api_key = _encrypt(value or '') or ''

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def clean(self):
        if self.default_scope not in SHARING_SCOPE_VALUES:
            raise ValidationError({'default_scope': 'Unsupported sharing scope.'})
        if self.auto_pull_schedule not in HEFAISTOS_AUTO_PULL_SCHEDULE_VALUES:
            raise ValidationError({'auto_pull_schedule': 'Unsupported auto pull schedule.'})
        if self.allow_self_signed and self.verify_ssl:
            raise ValidationError(
                {'verify_ssl': 'Disable strict SSL verification when allow_self_signed is enabled.'}
            )
        if self.tls_cert_fingerprint:
            normalized = ''.join(ch for ch in self.tls_cert_fingerprint if ch.isalnum()).lower()
            if len(normalized) != 64:
                raise ValidationError(
                    {'tls_cert_fingerprint': 'Fingerprint must be a SHA-256 hex value (64 hex chars).'}
                )


class HefaistosInboundShareKey(models.Model):
    """Inbound API keys allowing remote instances to PULL read-only data."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='hefaistos_inbound_share_keys',
    )
    name = models.CharField(max_length=120)
    key_hash = models.CharField(
        max_length=64,
        unique=True,
        help_text='SHA-256 hex hash of the raw inbound key.',
    )
    key_hint = models.CharField(
        max_length=24,
        blank=True,
        default='',
        help_text='Non-sensitive key preview for admins (e.g. prefix/suffix).',
    )
    allowed_scopes = models.JSONField(
        default=list,
        blank=True,
        help_text='Allowed pull scopes for this key: WORKBENCH, RULES, ACH, ADVOPS, ALL.',
    )
    enforce_tag_filter = models.BooleanField(
        default=False,
        help_text='When enabled, remote pulls are restricted to items matching required_tags.',
    )
    required_tags = models.JSONField(
        default=list,
        blank=True,
        help_text='Required tags for export eligibility when enforce_tag_filter is enabled (e.g. ["PULL"]).',
    )
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        'identity.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_hefaistos_inbound_share_keys',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = [('organization', 'name')]
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['key_hash']),
        ]
        verbose_name = 'HEFAISTOS Inbound Share Key'
        verbose_name_plural = 'HEFAISTOS Inbound Share Keys'

    def __str__(self):
        return f'{self.name} ({self.organization.name})'

    def clean(self):
        invalid = [
            scope for scope in (self.allowed_scopes or [])
            if str(scope).upper() not in SHARING_SCOPE_VALUES
        ]
        if invalid:
            raise ValidationError(
                {'allowed_scopes': f'Unsupported scopes: {", ".join(sorted(set(map(str, invalid))))}'}
            )

        normalized_tags: list[str] = []
        for raw_tag in (self.required_tags or []):
            tag = str(raw_tag or '').strip()
            if not tag:
                continue
            if tag.casefold() in {existing.casefold() for existing in normalized_tags}:
                continue
            normalized_tags.append(tag)

        self.required_tags = normalized_tags

        if self.enforce_tag_filter and not self.required_tags:
            raise ValidationError({'required_tags': 'At least one required tag is needed when tag filtering is enabled.'})


class HefaistosPullJob(models.Model):
    """Audit trail and status history for remote PULL synchronization jobs."""

    class Status(models.TextChoices):
        QUEUED = 'QUEUED', 'Queued'
        PROCESSING = 'PROCESSING', 'Processing'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='hefaistos_pull_jobs',
    )
    peer = models.ForeignKey(
        HefaistosRemotePeer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pull_jobs',
    )
    requested_scope = models.CharField(max_length=16, choices=SHARING_SCOPE_CHOICES, default='ALL')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    summary = models.JSONField(default=dict, blank=True)
    message = models.TextField(blank=True, default='')
    triggered_by = models.ForeignKey(
        'identity.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hefaistos_pull_jobs',
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'HEFAISTOS Pull Job'
        verbose_name_plural = 'HEFAISTOS Pull Jobs'

    def __str__(self):
        return f'PullJob({self.id}) [{self.status}]'
