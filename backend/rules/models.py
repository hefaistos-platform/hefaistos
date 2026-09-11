import uuid
from django.db import models
from organizations.models import Organization
"""
Avoid importing PlaybookGraph directly to prevent circular imports with
`playbooks.models` which imports `rules.models` for M2M. Use string reference
('playbooks.PlaybookGraph') in the OneToOneField instead.
"""
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken

# --- Encryption Helper ---
# We initialize Fernet with the key from our settings
try:
    FERNET = Fernet(settings.FIELD_ENCRYPTION_KEY)
except Exception:
    FERNET = None  # Handle case where key is not set

def encrypt_field(text):
    if not FERNET or not text:
        return None
    return FERNET.encrypt(text.encode()).decode()

def decrypt_field(encrypted_text):
    if not FERNET or not encrypted_text:
        return None
    try:
        return FERNET.decrypt(encrypted_text.encode()).decode()
    except InvalidToken:
        return None  # Or raise an error


# --- Original RuleRepository Model (from Sprint 2) ---
class RuleRepository(models.Model):
    # Keep default auto PK (BigAutoField) to match existing initial migration
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="rule_repositories")
    name = models.CharField(max_length=100)
    # Temporarily nullable to allow migration without one-off default; enforce later after backfill.
    git_url = models.URLField(max_length=500, help_text="Clone URL (e.g., https://github.com/SigmaHQ/sigma.git)", blank=True, null=True)
    class GitProvider(models.TextChoices):
        AUTO = 'AUTO', 'Auto-detect'
        GITHUB = 'GITHUB', 'GitHub'
        GITLAB = 'GITLAB', 'GitLab'
        GITEA = 'GITEA', 'Gitea'

    provider = models.CharField(
        max_length=16,
        choices=GitProvider.choices,
        default=GitProvider.AUTO,
        help_text="Git repository provider. AUTO derives provider from git_url host."
    )
    api_base_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Optional custom API base URL for self-hosted providers (e.g., https://gitlab.example.com/api/v4)."
    )
    verify_ssl = models.BooleanField(
        default=True,
        help_text="Verify TLS certificates for repository API calls. Disable only for trusted self-signed endpoints.",
    )

    # --- NEW ENCRYPTED FIELDS ---
    username = models.CharField(max_length=512, blank=True, null=True, help_text="Encrypted username or app ID")
    _token = models.TextField(blank=True, null=True, db_column='token', help_text="Encrypted access token (do not access directly)")

    # --- NEW "token" property ---
    @property
    def token(self):
        """Returns the decrypted token."""
        return decrypt_field(self._token)

    @token.setter
    def token(self, value):
        """Encrypts and sets the token."""
        self._token = encrypt_field(value)

    # --- END NEW FIELDS ---

    last_synced = models.DateTimeField(null=True, blank=True)

    # --- SCHEDULED PULL FIELDS ---
    class PullSchedule(models.TextChoices):
        DISABLED = 'DISABLED', 'Disabled'
        EVERY_24H = '24H', 'Every 24 hours'
        EVERY_48H = '48H', 'Every 48 hours'
        EVERY_72H = '72H', 'Every 72 hours'
        WEEKLY = 'WEEKLY', 'Weekly'

    auto_pull_schedule = models.CharField(
        max_length=20,
        choices=PullSchedule.choices,
        default=PullSchedule.DISABLED,
        help_text="Schedule for automatic pulls from this repository"
    )
    auto_pull_enabled = models.BooleanField(default=False, help_text="Whether automatic pulls are enabled")
    next_scheduled_pull = models.DateTimeField(null=True, blank=True, help_text="When the next scheduled pull should occur")
    # --- END SCHEDULED PULL FIELDS ---

    # --- RAG TEMPLATE SYNC FIELDS ---
    class RAGSyncSchedule(models.TextChoices):
        DISABLED = 'DISABLED', 'Disabled'
        EVERY_24H = '24H', 'Every 24 hours'
        EVERY_48H = '48H', 'Every 48 hours'
        EVERY_72H = '72H', 'Every 72 hours'
        WEEKLY = 'WEEKLY', 'Weekly'

    class RAGSyncStatus(models.TextChoices):
        IDLE = 'IDLE', 'Idle'
        QUEUED = 'QUEUED', 'Queued'
        RUNNING = 'RUNNING', 'Running'
        PARTIAL = 'PARTIAL', 'Partial'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'

    rag_sync_enabled = models.BooleanField(
        default=False,
        help_text="Whether RAG template sync from this repository is enabled",
    )
    rag_sync_schedule = models.CharField(
        max_length=20,
        choices=RAGSyncSchedule.choices,
        default=RAGSyncSchedule.DISABLED,
        help_text="Schedule for automatic RAG template sync from this repository",
    )
    rag_dataset_path = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text="Repository-relative dataset path or glob pattern for JSONL/KQL sources.",
    )
    rag_branch = models.CharField(
        max_length=128,
        blank=True,
        default='main',
        help_text="Git branch used for RAG dataset sync.",
    )
    rag_next_scheduled_sync = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the next scheduled RAG sync should occur",
    )
    rag_last_synced = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the most recent completed RAG sync attempt.",
    )
    rag_last_sync_status = models.CharField(
        max_length=16,
        choices=RAGSyncStatus.choices,
        default=RAGSyncStatus.IDLE,
        blank=True,
        help_text="Status of the most recent RAG sync lifecycle.",
    )
    rag_last_sync_status_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when rag_last_sync_status was last updated.",
    )
    rag_last_sync_error = models.TextField(
        blank=True,
        default='',
        help_text="Last RAG sync error message (if any).",
    )
    rag_last_synced_templates = models.PositiveIntegerField(
        default=0,
        help_text="Number of templates synchronized in the latest successful RAG sync.",
    )
    # --- END RAG TEMPLATE SYNC FIELDS ---

    def __str__(self):
        return self.name

    # Convenience read-only aliases expected by newer API layer
    @property
    def url(self):
        return self.git_url

    @property
    def last_sync(self):
        return self.last_synced

    class Meta:
        verbose_name_plural = "Rule Repositories"
        unique_together = ('organization', 'name')


class RuleRepositoryRAGFileStatus(models.Model):
    class IngestionStatus(models.TextChoices):
        INGESTED = 'INGESTED', 'Ingested'
        FAILED = 'FAILED', 'Failed'

    repository = models.ForeignKey(
        RuleRepository,
        on_delete=models.CASCADE,
        related_name='rag_files',
    )
    source_path = models.CharField(max_length=500)
    source_branch = models.CharField(max_length=128, blank=True, default='main')
    language = models.CharField(max_length=16, default='KQL')
    ingestion_status = models.CharField(
        max_length=16,
        choices=IngestionStatus.choices,
        default=IngestionStatus.FAILED,
    )
    templates_count = models.PositiveIntegerField(default=0)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default='')

    used_in_generation = models.BooleanField(default=False)
    usage_count = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('repository', 'source_path', 'source_branch', 'language')
        ordering = ['source_path']
        verbose_name = 'RAG File Status'
        verbose_name_plural = 'RAG File Statuses'

    def __str__(self):
        return f"{self.repository.name}:{self.source_path} ({self.ingestion_status})"


class DetectionRule(models.Model):
    # Keep default auto PK (BigAutoField) to match existing initial migration
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="detection_rules")
    repository = models.ForeignKey(RuleRepository, on_delete=models.CASCADE, related_name="rules")
    title = models.CharField(max_length=255)
    sigma_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    status = models.CharField(max_length=50, null=True, blank=True)
    FORMAT_CHOICES = (
        ('KQL', 'Kusto Query Language'),
        ('EQL', 'Elastic EQL'),
        ('WAZUH', 'Wazuh XML'),
        ('SPL', 'Splunk SPL'),
        ('AQL', 'IBM QRadar AQL'),
        ('OPENTIDE', 'OpenTide Multi-Platform'),
        ('OTHER', 'Other'),
    )
    format = models.CharField(max_length=10, choices=FORMAT_CHOICES, default='KQL')
    description = models.TextField(null=True, blank=True)
    author = models.CharField(max_length=255, null=True, blank=True)
    raw_content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    # Link back to the PlaybookGraph that created/owns this rule.
    # Allow multiple rules per playbook (one per format).
    playbook = models.ForeignKey(
        'playbooks.PlaybookGraph',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='linked_rules'
    )

    def __str__(self):
        return self.title

class KQLTable(models.Model):
    """
    Cache of KQL tables for autocomplete suggestions (Phase 2).
    """
    table_name = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "KQL Table"
        verbose_name_plural = "KQL Tables"
        ordering = ['table_name']

    def __str__(self):
        return self.table_name


class KQLField(models.Model):
    """
    Cache of KQL fields per table for autocomplete suggestions (Phase 2).
    """
    table = models.ForeignKey(KQLTable, on_delete=models.CASCADE, related_name='fields')
    field_name = models.CharField(max_length=100, db_index=True)
    field_type = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('table', 'field_name')
        ordering = ['table', 'field_name']
        verbose_name = "KQL Field"
        verbose_name_plural = "KQL Fields"

    def __str__(self):
        return f"{self.table.table_name}.{self.field_name}"


class FieldMapping(models.Model):
    """
    Mapping between SIGMA fields and KQL fields for the same data source.
    Used for cross-format suggestions.
    """
    data_source = models.ForeignKey('data_catalog.DataSource', on_delete=models.CASCADE, related_name='field_mappings')
    sigma_field = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    kql_field = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    mapping_type = models.CharField(
        max_length=20,
        choices=[
            ('direct', 'Direct 1:1 mapping'),
            ('derived', 'Derived/calculated field'),
            ('unsupported', 'Not available in target format'),
        ],
        default='direct'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('data_source', 'sigma_field', 'kql_field')
        ordering = ['data_source', 'sigma_field']
        verbose_name = "Field Mapping"
        verbose_name_plural = "Field Mappings"

    def __str__(self):
        return f"{self.data_source.name}: {self.sigma_field} → {self.kql_field}"

class AutocompleteEvent(models.Model):
    """
    Lightweight telemetry for autocomplete usage.
    Records format, position, suggestion count, data source, and a small context snapshot.
    """
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='autocomplete_events')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='autocomplete_events')
    format = models.CharField(max_length=10, db_index=True)
    position = models.IntegerField()
    suggestions_count = models.IntegerField()
    data_source_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    context_snapshot = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Autocomplete Event'
        verbose_name_plural = 'Autocomplete Events'

    def __str__(self):
        return f"{self.format} @ {self.position} suggestions={self.suggestions_count}"
