from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken
import uuid

def _get_fernet():
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
    if key:
        try:
            return Fernet(key)
        except Exception:
            return None
    return None

def _encrypt(value: str) -> str:
    if not value:
        return value
    if value.startswith('enc:'):
        return value  # already encrypted
    f = _get_fernet()
    if not f:
        return value  # encryption disabled
    return 'enc:' + f.encrypt(value.encode()).decode()

def _decrypt(value: str) -> str:
    if not value:
        return ''
    if not value.startswith('enc:'):
        return value  # plaintext
    f = _get_fernet()
    if not f:
        return ''  # cannot decrypt without key
    token = value[4:]
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken:
        return ''  # corrupted or wrong key

class UserAISettings(models.Model):
    """
    Stores per-user API keys. 
    WARNING: In production, use Fernet encryption for these fields.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_settings')
    
    # Use TextField to support long provider keys (e.g., OpenAI Project keys)
    openai_api_key = models.TextField(blank=True, null=True)
    gemini_api_key = models.TextField(blank=True, null=True)
    claude_api_key = models.TextField(blank=True, null=True)
    
    preferred_model = models.CharField(
        max_length=50,
        choices=[
            # OpenAI GPT Models
            ('GPT-5.5', 'GPT-5.5'),
            ('GPT-5.4', 'GPT-5.4'),
            ('GPT-5.4-MINI', 'GPT-5.4 Mini'),
            # Google Gemini Models
            ('GEMINI-3.1-PRO-PREVIEW', 'Gemini 3.1 Pro Preview'),
            ('GEMINI-3.5-FLASH', 'Gemini 3.5 Flash'),
            ('GEMINI-3-FLASH-PREVIEW', 'Gemini 3 Flash Preview'),
            ('GEMINI-3.1-FLASH-LITE', 'Gemini 3.1 Flash Lite'),
            ('GEMINI-3.1-FLASH-LITE-PREVIEW', 'Gemini 3.1 Flash Lite Preview'),
            # Anthropic Claude Models
            ('CLAUDE-OPUS-4.7', 'Claude Opus 4.7'),
            ('CLAUDE-SONNET-4.6', 'Claude Sonnet 4.6'),
            ('CLAUDE-HAIKU-4.5-20251001', 'Claude Haiku 4.5 (20251001)'),
        ],
        default='GEMINI-3.5-FLASH'
    )

    use_org_ai = models.BooleanField(
        default=False,
        help_text="When True, use the organization-wide AI model instead of personal API keys.",
    )

    # OpenTIDE auto-enrichment settings
    enable_auto_enrichment = models.BooleanField(
        default=True,
        help_text="Automatically enrich OpenTIDE metadata using AI when information is missing",
    )

    auto_generate_bdr = models.BooleanField(
        default=True,
        help_text="Automatically generate BDR schema for compliance-driven detections",
    )

    auto_enrich_response = models.BooleanField(
        default=True,
        help_text="Automatically generate response procedures and supporting searches",
    )

    auto_map_platforms = models.BooleanField(
        default=True,
        help_text="Automatically extract platforms and targets from technical context",
    )

    def __str__(self):
        return f"AI Settings for {self.user.username}"

    # --- Encryption Helpers ---
    def save(self, *args, **kwargs):
        # Encrypt keys if not already encrypted.
        self.openai_api_key = _encrypt(self.openai_api_key or '')
        self.gemini_api_key = _encrypt(self.gemini_api_key or '')
        self.claude_api_key = _encrypt(self.claude_api_key or '')
        super().save(*args, **kwargs)

    def get_openai_key(self) -> str:
        return _decrypt(self.openai_api_key or '')

    def get_gemini_key(self) -> str:
        return _decrypt(self.gemini_api_key or '')

    def get_claude_key(self) -> str:
        return _decrypt(self.claude_api_key or '')

    # Stub methods so the engine can call these on UserAISettings without AttributeError
    def get_ollama_url(self) -> str:
        return ''

    def get_ollama_model(self) -> str:
        return ''

    def get_azure_openai_key(self) -> str:
        return ''

    def get_azure_openai_endpoint(self) -> str:
        return ''

    def get_azure_openai_deployment(self) -> str:
        return ''


class AIGenerationTask(models.Model):
    """Async task for AI rule generation, improvement suggestions, and similar-rule generation."""

    class TaskType(models.TextChoices):
        GENERATE_RULE = 'GENERATE_RULE', 'Generate Rule'
        SUGGEST_IMPROVEMENTS = 'SUGGEST_IMPROVEMENTS', 'Suggest Improvements'
        GENERATE_SIMILAR = 'GENERATE_SIMILAR', 'Generate Similar Rules'
        POPULATE_THREAT_REPORT = 'POPULATE_THREAT_REPORT', 'Populate Workbench from Threat Report'

    class TaskStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_generation_tasks',
    )
    task_type = models.CharField(max_length=30, choices=TaskType.choices)
    status = models.CharField(
        max_length=20,
        choices=TaskStatus.choices,
        default=TaskStatus.PENDING,
    )
    # Input payload stored as JSON so a single model covers all task types
    input_data = models.JSONField()
    # Output result stored as JSON when COMPLETED
    result_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"AIGenerationTask({self.id}, {self.task_type}, {self.status})"


class SharedAIProfile(models.Model):
    """
    System-wide shared AI profile managed by platform superusers.
    Organizations can be assigned this profile with optional lock enforcement.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)

    # Ollama integration
    ollama_base_url = models.CharField(max_length=512, blank=True, default='')
    ollama_model = models.CharField(max_length=100, blank=True, default='')

    # Cloud provider API keys (encrypted at rest)
    openai_api_key = models.TextField(blank=True, null=True)
    gemini_api_key = models.TextField(blank=True, null=True)
    claude_api_key = models.TextField(blank=True, null=True)

    # Azure OpenAI
    azure_openai_endpoint = models.CharField(max_length=512, blank=True, default='')
    azure_openai_api_key = models.TextField(blank=True, null=True)
    azure_openai_deployment = models.CharField(max_length=100, blank=True, default='')

    org_preferred_model = models.CharField(max_length=50, blank=True, default='')
    ollama_enabled = models.BooleanField(default=True)
    openai_enabled = models.BooleanField(default=True)
    gemini_enabled = models.BooleanField(default=True)
    claude_enabled = models.BooleanField(default=True)
    azure_openai_enabled = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_shared_ai_profiles',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Shared AI Profile"
        verbose_name_plural = "Shared AI Profiles"
        ordering = ['name']

    def __str__(self):
        return f"Shared AI Profile: {self.name}"

    def save(self, *args, **kwargs):
        self.openai_api_key = _encrypt(self.openai_api_key or '')
        self.gemini_api_key = _encrypt(self.gemini_api_key or '')
        self.claude_api_key = _encrypt(self.claude_api_key or '')
        self.azure_openai_api_key = _encrypt(self.azure_openai_api_key or '')
        super().save(*args, **kwargs)

    def get_openai_key(self) -> str:
        return _decrypt(self.openai_api_key or '')

    def get_gemini_key(self) -> str:
        return _decrypt(self.gemini_api_key or '')

    def get_claude_key(self) -> str:
        return _decrypt(self.claude_api_key or '')

    def get_azure_openai_key(self) -> str:
        return _decrypt(self.azure_openai_api_key or '')

    def get_azure_openai_endpoint(self) -> str:
        return self.azure_openai_endpoint or ''

    def get_azure_openai_deployment(self) -> str:
        return self.azure_openai_deployment or ''

    def get_ollama_url(self) -> str:
        return self.ollama_base_url or ''

    def get_ollama_model(self) -> str:
        return self.ollama_model or ''

    @property
    def has_ollama(self) -> bool:
        return bool(self.ollama_base_url and self.ollama_model and self.ollama_enabled)

    @property
    def has_openai(self) -> bool:
        return bool(self.get_openai_key() and self.openai_enabled)

    @property
    def has_gemini(self) -> bool:
        return bool(self.get_gemini_key() and self.gemini_enabled)

    @property
    def has_claude(self) -> bool:
        return bool(self.get_claude_key() and self.claude_enabled)

    @property
    def has_azure_openai(self) -> bool:
        return bool(self.azure_openai_endpoint and self.get_azure_openai_key() and self.azure_openai_enabled)

    @property
    def has_any_provider(self) -> bool:
        return self.has_ollama or self.has_openai or self.has_gemini or self.has_claude or self.has_azure_openai

    @property
    def preferred_model(self) -> str:
        if self.org_preferred_model:
            return self.org_preferred_model
        if self.has_ollama:
            return 'OLLAMA'
        if self.has_openai:
            return 'GPT-5.5'
        if self.has_gemini:
            return 'GEMINI-3.5-FLASH'
        if self.has_claude:
            return 'CLAUDE-SONNET-4.6'
        if self.has_azure_openai:
            return 'AZURE-OPENAI'
        return 'NONE'


class OrgAISettings(models.Model):
    """
    Organization-wide AI settings managed by admins.
    Supports Ollama (self-hosted LLM) and cloud providers (OpenAI, Gemini, Claude).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='ai_settings',
    )
    shared_profile = models.ForeignKey(
        SharedAIProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_organizations',
    )
    shared_profile_locked = models.BooleanField(
        default=False,
        help_text='When enabled, this organization must use the assigned shared AI profile.',
    )

    # Ollama integration
    ollama_base_url = models.CharField(
        max_length=512,
        blank=True,
        default='',
        help_text="Ollama server base URL, e.g. http://ollama:11434",
    )
    ollama_model = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Ollama model name, e.g. llama3, mistral, codellama",
    )

    # Cloud provider API keys (encrypted at rest)
    openai_api_key = models.TextField(blank=True, null=True)
    gemini_api_key = models.TextField(blank=True, null=True)
    claude_api_key = models.TextField(blank=True, null=True)

    # Azure OpenAI (Azure Foundry) integration
    azure_openai_endpoint = models.CharField(
        max_length=512,
        blank=True,
        default='',
        help_text="Azure OpenAI endpoint URL, e.g. https://YOUR_RESOURCE.openai.azure.com",
    )
    azure_openai_api_key = models.TextField(blank=True, null=True)
    azure_openai_deployment = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Azure OpenAI deployment name",
    )

    # Preferred model for org-wide usage (overrides user's personal preferred_model when use_org_ai=True)
    org_preferred_model = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="Default model for org-wide AI usage, e.g. GPT-5.5, GEMINI-3.5-FLASH, CLAUDE-SONNET-4.6, OLLAMA",
    )

    # Enable/disable flags per provider (configuration is preserved when disabled)
    ollama_enabled = models.BooleanField(default=True)
    openai_enabled = models.BooleanField(default=True)
    gemini_enabled = models.BooleanField(default=True)
    claude_enabled = models.BooleanField(default=True)
    azure_openai_enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Organization AI Settings"
        verbose_name_plural = "Organization AI Settings"

    def __str__(self):
        return f"Org AI Settings for {self.organization.name}"

    # --- Encryption Helpers ---
    def save(self, *args, **kwargs):
        self.openai_api_key = _encrypt(self.openai_api_key or '')
        self.gemini_api_key = _encrypt(self.gemini_api_key or '')
        self.claude_api_key = _encrypt(self.claude_api_key or '')
        self.azure_openai_api_key = _encrypt(self.azure_openai_api_key or '')
        super().save(*args, **kwargs)

    def get_openai_key(self) -> str:
        return _decrypt(self.openai_api_key or '')

    def get_gemini_key(self) -> str:
        return _decrypt(self.gemini_api_key or '')

    def get_claude_key(self) -> str:
        return _decrypt(self.claude_api_key or '')

    def get_azure_openai_key(self) -> str:
        return _decrypt(self.azure_openai_api_key or '')

    def get_azure_openai_endpoint(self) -> str:
        return self.azure_openai_endpoint or ''

    def get_azure_openai_deployment(self) -> str:
        return self.azure_openai_deployment or ''

    def get_ollama_url(self) -> str:
        return self.ollama_base_url or ''

    def get_ollama_model(self) -> str:
        return self.ollama_model or ''

    @property
    def has_ollama(self) -> bool:
        return bool(self.ollama_base_url and self.ollama_model and self.ollama_enabled)

    @property
    def has_openai(self) -> bool:
        return bool(self.get_openai_key() and self.openai_enabled)

    @property
    def has_gemini(self) -> bool:
        return bool(self.get_gemini_key() and self.gemini_enabled)

    @property
    def has_claude(self) -> bool:
        return bool(self.get_claude_key() and self.claude_enabled)

    @property
    def has_azure_openai(self) -> bool:
        return bool(self.azure_openai_endpoint and self.get_azure_openai_key() and self.azure_openai_enabled)

    @property
    def has_any_provider(self) -> bool:
        return self.has_ollama or self.has_openai or self.has_gemini or self.has_claude or self.has_azure_openai

    @property
    def preferred_model(self) -> str:
        """Return the effective preferred model for org-wide AI usage."""
        if self.org_preferred_model:
            return self.org_preferred_model
        # Auto-detect based on configured providers
        if self.has_ollama:
            return 'OLLAMA'
        if self.has_openai:
            return 'GPT-5.5'
        if self.has_gemini:
            return 'GEMINI-3.5-FLASH'
        if self.has_claude:
            return 'CLAUDE-SONNET-4.6'
        if self.has_azure_openai:
            return 'AZURE-OPENAI'
        return 'NONE'

    @property
    def has_assigned_shared_profile(self) -> bool:
        return bool(self.shared_profile_id and self.shared_profile and self.shared_profile.is_active)

    @property
    def can_edit_custom_settings(self) -> bool:
        return not (self.has_assigned_shared_profile and self.shared_profile_locked)

    @property
    def config_source(self) -> str:
        if self.has_assigned_shared_profile and self.shared_profile_locked and self.shared_profile.has_any_provider:
            return 'SHARED_LOCKED'
        if self.has_any_provider:
            return 'CUSTOM'
        if self.has_assigned_shared_profile and self.shared_profile.has_any_provider:
            return 'SHARED'
        return 'CUSTOM'

    def get_effective_settings(self):
        if self.has_assigned_shared_profile and self.shared_profile_locked and self.shared_profile.has_any_provider:
            return self.shared_profile
        if self.has_any_provider:
            return self
        if self.has_assigned_shared_profile and self.shared_profile.has_any_provider:
            return self.shared_profile
        return self
