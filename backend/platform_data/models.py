import uuid
from django.db import models
from django.conf import settings

class MitreDomain(models.TextChoices):
    ENTERPRISE = 'enterprise-attack', 'Enterprise'
    MOBILE = 'mobile-attack', 'Mobile'
    ICS = 'ics-attack', 'ICS'

class MitreAttackTechnique(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    technique_id = models.CharField(max_length=20)
    stix_id = models.CharField(max_length=100, unique=True, null=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    url = models.URLField(max_length=512)
    domain = models.CharField(max_length=50, choices=MitreDomain.choices, default=MitreDomain.ENTERPRISE)
    # Tactic(s) the technique belongs to (e.g. "Execution", "Defense Evasion")
    tactic = models.CharField(
        max_length=255,
        blank=True,
        help_text="ATT&CK tactic(s) for this technique (comma-separated if multiple)",
    )
    # Lifecycle flags imported from the ATT&CK Excel 'revoked' / 'deprecated' columns
    revoked = models.BooleanField(
        default=False,
        help_text="Technique has been revoked by MITRE (superseded or removed)",
    )
    deprecated = models.BooleanField(
        default=False,
        help_text="Technique has been deprecated by MITRE",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['technique_id', 'domain'], name='unique_technique_per_domain')
        ]

    def __str__(self): return f"{self.technique_id}: {self.name}"

# --- NEW MODEL ---
class MitreDetectionStrategy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stix_id = models.CharField(max_length=100, unique=True)
    def_id = models.CharField(max_length=50, null=True) # e.g. DET0001
    name = models.CharField(max_length=255)
    url = models.URLField(max_length=512, null=True)
    domain = models.CharField(max_length=50, choices=MitreDomain.choices, default=MitreDomain.ENTERPRISE)
    
    # The crucial link: Strategy -> detects -> Technique
    techniques = models.ManyToManyField(MitreAttackTechnique, related_name="detection_strategies", blank=True)

    def __str__(self): return f"{self.def_id}: {self.name}"

    class Meta:
        verbose_name_plural = "Mitre detection strategies"

class MitreAnalytic(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stix_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField()
    domain = models.CharField(max_length=50, choices=MitreDomain.choices, default=MitreDomain.ENTERPRISE)
    
    # UPDATED LINK: Analytic belongs to a Strategy
    detection_strategy = models.ForeignKey(MitreDetectionStrategy, on_delete=models.SET_NULL, null=True, blank=True, related_name="analytics")

    def __str__(self): return self.name

# (Keep DataSource and DataComponent models if you wish, but they are secondary in this chain)
class MitreDataSource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stix_id = models.CharField(max_length=100, unique=True, null=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.name

class MitreDataComponent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stix_id = models.CharField(max_length=100, unique=True, null=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    domain = models.CharField(max_length=50, choices=MitreDomain.choices, default=MitreDomain.ENTERPRISE)
    
    data_source = models.ForeignKey(MitreDataSource, on_delete=models.CASCADE, related_name="components", null=True)
    techniques = models.ManyToManyField(MitreAttackTechnique, related_name="data_components", blank=True)

    def __str__(self):
        return f"{self.data_source.name}: {self.name}"

# --- 4. ICS Technique ---
class MitreIcsTechnique(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    technique_id = models.CharField(max_length=20, unique=True, help_text="e.g., T0800")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    url = models.URLField(max_length=512)

    def __str__(self):
        return f"{self.technique_id}: {self.name}"

# --- 5. Mobile Technique ---
class MitreMobileTechnique(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    technique_id = models.CharField(max_length=20, unique=True, help_text="e.g., T1400")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    url = models.URLField(max_length=512)

    def __str__(self):
        return f"{self.technique_id}: {self.name}"

# --- D3FEND MODELS ---

class D3fendDefensiveTechnique(models.Model):
    """D3FEND defensive technique (e.g., D3-PSA Process Spawn Analysis)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    d3fend_id = models.CharField(max_length=20, unique=True)  # e.g., "D3-PSA"
    name = models.CharField(max_length=255)
    definition = models.TextField(blank=True)
    iri = models.URLField(max_length=512, blank=True)  # Ontology IRI reference
    
    # Hierarchical structure
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')
    tactic = models.CharField(max_length=100, blank=True)  # Detect, Harden, Deceive, Evict, Isolate
    
    class Meta:
        ordering = ['d3fend_id']
    
    def __str__(self):
        return f"{self.d3fend_id}: {self.name}"


class D3fendDigitalArtifact(models.Model):
    """D3FEND Digital Artifacts that techniques analyze/produce"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    artifact_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    definition = models.TextField(blank=True)
    iri = models.URLField(max_length=512, blank=True)
    
    # Link to techniques that use this artifact
    techniques = models.ManyToManyField(D3fendDefensiveTechnique, related_name='digital_artifacts', blank=True)
    
    def __str__(self):
        return self.name


class D3fendAttackMapping(models.Model):
    """ATT&CK → D3FEND countermeasure mappings"""
    attack_technique = models.ForeignKey(MitreAttackTechnique, on_delete=models.CASCADE, related_name='d3fend_countermeasures')
    d3fend_technique = models.ForeignKey(D3fendDefensiveTechnique, on_delete=models.CASCADE, related_name='countered_attacks')
    relationship = models.CharField(max_length=50, default='counters')
    
    class Meta:
        unique_together = ['attack_technique', 'd3fend_technique']
    
    def __str__(self):
        return f"{self.d3fend_technique.d3fend_id} counters {self.attack_technique.technique_id}"


# ---------------------------------------------------------------------------
# MITRE ATLAS
# ---------------------------------------------------------------------------

class AtlasTactic(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    atlas_id = models.CharField(max_length=20, unique=True, db_index=True)  # e.g., AML.TA0001
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    references = models.JSONField(default=list, blank=True)
    attack_reference = models.JSONField(default=dict, blank=True)
    created_date = models.DateField(null=True, blank=True)
    modified_date = models.DateField(null=True, blank=True)
    atlas_uuid = models.UUIDField(null=True, blank=True)
    object_type = models.CharField(max_length=50, default='tactic', blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['atlas_id']

    def __str__(self):
        return f"{self.atlas_id}: {self.name}"


class AtlasTechnique(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    atlas_id = models.CharField(max_length=20, unique=True, db_index=True)  # e.g., AML.T0000.001
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    references = models.JSONField(default=list, blank=True)
    platforms = models.JSONField(default=list, blank=True)
    maturity = models.CharField(max_length=50, blank=True, default='')
    attack_reference = models.JSONField(default=dict, blank=True)
    created_date = models.DateField(null=True, blank=True)
    modified_date = models.DateField(null=True, blank=True)
    atlas_uuid = models.UUIDField(null=True, blank=True)
    object_type = models.CharField(max_length=50, default='technique', blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['atlas_id']

    def __str__(self):
        return f"{self.atlas_id}: {self.name}"


class AtlasMitigation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    atlas_id = models.CharField(max_length=20, unique=True, db_index=True)  # e.g., AML.M0004
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    references = models.JSONField(default=list, blank=True)
    lifecycle_phases = models.JSONField(default=list, blank=True)
    categories = models.JSONField(default=list, blank=True)
    created_date = models.DateField(null=True, blank=True)
    modified_date = models.DateField(null=True, blank=True)
    atlas_uuid = models.UUIDField(null=True, blank=True)
    object_type = models.CharField(max_length=50, default='mitigation', blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['atlas_id']

    def __str__(self):
        return f"{self.atlas_id}: {self.name}"


class AtlasCaseStudy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    atlas_id = models.CharField(max_length=20, unique=True, db_index=True)  # e.g., AML.CS0000
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    references = models.JSONField(default=list, blank=True)
    case_study_type = models.CharField(max_length=50, blank=True, default='')
    actor = models.CharField(max_length=255, blank=True, default='')
    target = models.TextField(blank=True, default='')
    reporter = models.CharField(max_length=255, blank=True, default='')
    start_date = models.DateField(null=True, blank=True)
    start_date_granularity = models.CharField(max_length=20, blank=True, default='')
    end_date = models.DateField(null=True, blank=True)
    end_date_granularity = models.CharField(max_length=20, blank=True, default='')
    created_date = models.DateField(null=True, blank=True)
    modified_date = models.DateField(null=True, blank=True)
    atlas_uuid = models.UUIDField(null=True, blank=True)
    object_type = models.CharField(max_length=50, default='case-study', blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['atlas_id']

    def __str__(self):
        return f"{self.atlas_id}: {self.name}"


class AtlasRelationship(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_atlas_id = models.CharField(max_length=20, db_index=True)
    target_atlas_id = models.CharField(max_length=20, db_index=True)
    relationship_type = models.CharField(max_length=50, db_index=True)  # e.g., mitigates, employs
    description = models.TextField(blank=True)
    tactic_atlas_id = models.CharField(max_length=20, blank=True, default='')
    step_id = models.CharField(max_length=20, blank=True, default='')
    leads_to = models.JSONField(default=list, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['source_atlas_id', 'step_id', 'target_atlas_id']
        constraints = [
            models.UniqueConstraint(
                fields=['source_atlas_id', 'target_atlas_id', 'relationship_type', 'step_id'],
                name='unique_atlas_relationship_step',
            ),
        ]

    def __str__(self):
        return f"{self.source_atlas_id} {self.relationship_type} {self.target_atlas_id}"


class AtlasImportJob(models.Model):
    """Tracks async MITRE ATLAS import runs triggered from the UI."""

    class Mode(models.TextChoices):
        REMOTE = 'REMOTE', 'Remote'
        LOCAL = 'LOCAL', 'Local'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_repo = models.URLField(max_length=512, default='https://github.com/mitre-atlas/atlas-data')
    source_ref = models.CharField(max_length=100, default='main', help_text="Git ref or commit SHA")
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.REMOTE)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    summary = models.JSONField(default=dict, blank=True)
    log = models.TextField(blank=True, default='')
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='atlas_import_jobs',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'ATLAS Import Job'
        verbose_name_plural = 'ATLAS Import Jobs'

    def __str__(self):
        return f"AtlasImportJob {self.source_ref} [{self.status}]"


# ---------------------------------------------------------------------------
# ShareTide Vocabulary Index
# ---------------------------------------------------------------------------

class ShareTideIndexEntry(models.Model):
    """
    An offline copy of ShareTide schema vocabulary entries.

    Mirrors the index files from
    https://github.com/OpenTideHQ/ShareTide/tree/main/Schemas/Indexes
    so that the OpenTIDE compiler can resolve valid vocabulary values without
    requiring an internet connection at compile time.

    Categories:
        - ``bdr_criticality``   – BDR criticality levels
        - ``bdr_domains``       – BDR applicable domains
        - ``bdr_targets``       – BDR target asset types
        - ``bdr_platforms``     – BDR operating platforms
        - ``mdr_alert_severities`` – MDR alert severity levels
        - ``mdr_responders``    – MDR responder team identifiers
        - ``dom_priorities``    – DOM detection priority levels
        - ``mdr_platforms``     – MDR supported SIEM/platform names
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Vocabulary category, e.g. 'bdr_platforms', 'mdr_responders'.",
    )
    value = models.CharField(
        max_length=255,
        help_text="Vocabulary entry value, e.g. 'Windows', 'High'.",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description or notes for this vocabulary entry.",
    )
    source_url = models.URLField(
        max_length=512,
        blank=True,
        help_text="URL to the upstream ShareTide index file.",
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Display ordering within category.",
    )

    class Meta:
        unique_together = [('category', 'value')]
        ordering = ['category', 'sort_order', 'value']
        verbose_name = "ShareTide Index Entry"
        verbose_name_plural = "ShareTide Index Entries"

    def __str__(self):
        return f"{self.category}: {self.value}"


# ---------------------------------------------------------------------------
# ATT&CK / Framework version tracking
# ---------------------------------------------------------------------------

class PlatformDataVersion(models.Model):
    """
    Records the version of each framework dataset currently loaded in the
    database.  Updated automatically by management import commands so that
    the admin UI and diagnostic endpoints can show freshness at a glance.
    """

    FRAMEWORK_CHOICES = [
        ('enterprise-attack', 'MITRE ATT&CK Enterprise'),
        ('ics-attack', 'MITRE ATT&CK ICS'),
        ('mobile-attack', 'MITRE ATT&CK Mobile'),
        ('d3fend', 'MITRE D3FEND'),
        ('atlas', 'MITRE ATLAS'),
        ('detection-chokepoints', 'Detection Chokepoints'),
        ('ade-framework', 'Adversarial Detection Engineering (ADE)'),
    ]

    framework = models.CharField(
        max_length=50,
        choices=FRAMEWORK_CHOICES,
        unique=True,
        help_text="Framework identifier (e.g. 'enterprise-attack')",
    )
    version = models.CharField(
        max_length=20,
        help_text="Loaded version string (e.g. '19.0')",
    )
    imported_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp of the last successful import for this framework",
    )

    class Meta:
        verbose_name = "Platform Data Version"
        verbose_name_plural = "Platform Data Versions"

    def __str__(self):
        return f"{self.get_framework_display()} v{self.version}"


# ---------------------------------------------------------------------------
# MITRE Import Jobs
# ---------------------------------------------------------------------------

class MitreImportJob(models.Model):
    """
    Tracks async MITRE ATT&CK import runs triggered from the UI.
    """

    class Mode(models.TextChoices):
        REMOTE = 'REMOTE', 'Remote'
        LOCAL = 'LOCAL', 'Local'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.CharField(max_length=20, help_text="ATT&CK version to import, e.g. '19.1'")
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.REMOTE)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    log = models.TextField(blank=True, default='')
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='mitre_import_jobs',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "MITRE Import Job"
        verbose_name_plural = "MITRE Import Jobs"

    def __str__(self):
        return f"MitreImportJob v{self.version} [{self.status}] @ {self.created_at}"


# ---------------------------------------------------------------------------
# Detection Chokepoints
# ---------------------------------------------------------------------------

class ChokepointSnapshot(models.Model):
    """
    Versioned imported snapshot of detection chokepoints.

    Import jobs create staged snapshots first. A snapshot is promoted to ACTIVE
    only after explicit approval so upstream changes are never auto-applied.
    """

    class Status(models.TextChoices):
        STAGED = 'STAGED', 'Staged'
        ACTIVE = 'ACTIVE', 'Active'
        FAILED = 'FAILED', 'Failed'
        ARCHIVED = 'ARCHIVED', 'Archived'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_repo = models.URLField(
        max_length=512,
        default='https://github.com/iimp0ster/detection-chokepoints',
        help_text="Upstream source repository URL.",
    )
    source_ref = models.CharField(
        max_length=128,
        default='main',
        help_text="Imported ref (branch/tag/commit).",
    )
    source_sha = models.CharField(
        max_length=64,
        blank=True,
        default='',
        help_text="Resolved upstream commit SHA when available.",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.STAGED)
    summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Import summary counters/diff metadata.",
    )
    entry_count = models.PositiveIntegerField(default=0)
    validation_errors = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='chokepoint_snapshots',
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at'], name='pld_chkp_snap_st_cr_idx'),
            models.Index(fields=['source_sha'], name='platform_chkp_snap_sha_idx'),
        ]
        verbose_name = "Chokepoint Snapshot"
        verbose_name_plural = "Chokepoint Snapshots"

    def __str__(self):
        rev = self.source_sha[:12] if self.source_sha else self.source_ref
        return f"ChokepointSnapshot {rev} [{self.status}]"


class ChokepointEntry(models.Model):
    """
    Normalized chokepoint record belonging to a specific snapshot.
    """

    class Confidence(models.TextChoices):
        UNKNOWN = 'UNKNOWN', 'Unknown'
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    snapshot = models.ForeignKey(
        ChokepointSnapshot,
        on_delete=models.CASCADE,
        related_name='entries',
    )
    entry_key = models.CharField(
        max_length=320,
        help_text="Stable key within a snapshot (derived from source path + title/id).",
    )
    source_path = models.CharField(max_length=512, blank=True, default='')
    source_hash = models.CharField(max_length=64, blank=True, default='')
    title = models.CharField(max_length=255)
    primary_technique_id = models.CharField(max_length=20, blank=True, default='')
    sub_technique_id = models.CharField(max_length=20, blank=True, default='')
    technique_name = models.CharField(max_length=255, blank=True, default='')
    tactic = models.CharField(max_length=120, blank=True, default='')
    telemetry_prerequisites = models.TextField(blank=True, default='')
    detection_context = models.TextField(blank=True, default='')
    platforms = models.JSONField(default=list, blank=True)
    data_components = models.JSONField(default=list, blank=True)
    detection_strategy_hints = models.JSONField(default=list, blank=True)
    native_rule_hints = models.JSONField(
        default=dict,
        blank=True,
        help_text="Engine-specific hints, e.g. {'kql': [...], 'spl': [...], 'wazuh_xml': [...]}",
    )
    references = models.JSONField(default=list, blank=True)
    tags = models.JSONField(default=list, blank=True)
    confidence = models.CharField(max_length=16, choices=Confidence.choices, default=Confidence.UNKNOWN)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['primary_technique_id', 'title']
        constraints = [
            models.UniqueConstraint(
                fields=['snapshot', 'entry_key'],
                name='unique_chokepoint_entry_per_snapshot',
            )
        ]
        indexes = [
            models.Index(fields=['primary_technique_id'], name='platform_chkp_ent_primary_idx'),
            models.Index(fields=['sub_technique_id'], name='platform_chkp_ent_subtech_idx'),
            models.Index(fields=['snapshot', 'primary_technique_id'], name='pld_chkp_ent_snap_pr_idx'),
        ]
        verbose_name = "Chokepoint Entry"
        verbose_name_plural = "Chokepoint Entries"

    def __str__(self):
        technique = self.sub_technique_id or self.primary_technique_id or "Unknown"
        return f"{technique}: {self.title}"


class ChokepointImportJob(models.Model):
    """
    Tracks async detection-chokepoints imports triggered from the management UI.
    """

    class Mode(models.TextChoices):
        REMOTE = 'REMOTE', 'Remote'
        LOCAL = 'LOCAL', 'Local'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_repo = models.URLField(
        max_length=512,
        default='https://github.com/iimp0ster/detection-chokepoints',
    )
    source_ref = models.CharField(max_length=128, default='main')
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.REMOTE)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    snapshot = models.ForeignKey(
        ChokepointSnapshot,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='import_jobs',
    )
    summary = models.JSONField(default=dict, blank=True)
    log = models.TextField(blank=True, default='')
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='chokepoint_import_jobs',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Chokepoint Import Job"
        verbose_name_plural = "Chokepoint Import Jobs"

    def __str__(self):
        return f"ChokepointImportJob {self.source_ref} [{self.status}] @ {self.created_at}"


# ---------------------------------------------------------------------------
# Adversarial Detection Engineering (ADE) framework
# ---------------------------------------------------------------------------

class AdeSnapshot(models.Model):
    """
    Versioned imported snapshot of the ADE framework (taxonomy, bug likelihood checks,
    rule-specific bypass records and in-the-wild records).

    Same lifecycle as ``ChokepointSnapshot``: imports create STAGED snapshots, an admin
    reviews the diff and promotes one to ACTIVE, and the previous ACTIVE snapshot is
    ARCHIVED so it can be rolled back to. Upstream changes are never auto-applied.
    """

    class Status(models.TextChoices):
        STAGED = 'STAGED', 'Staged'
        ACTIVE = 'ACTIVE', 'Active'
        FAILED = 'FAILED', 'Failed'
        ARCHIVED = 'ARCHIVED', 'Archived'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_repo = models.URLField(
        max_length=512,
        default='https://github.com/Adversarial-Detection-Engineering/Adversarial-Detection-Engineering-Framework',
        help_text="Upstream source repository URL.",
    )
    source_ref = models.CharField(max_length=128, default='main', help_text="Imported ref (branch/tag/commit).")
    source_sha = models.CharField(
        max_length=64, blank=True, default='',
        help_text="Resolved upstream commit SHA when available.",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.STAGED)
    summary = models.JSONField(
        default=dict, blank=True,
        help_text="Import counters per entry kind plus parser warnings.",
    )
    entry_count = models.PositiveIntegerField(default=0)
    validation_errors = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ade_snapshots',
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at'], name='pld_ade_snap_st_cr_idx'),
            models.Index(fields=['source_sha'], name='pld_ade_snap_sha_idx'),
        ]
        verbose_name = "ADE Snapshot"
        verbose_name_plural = "ADE Snapshots"

    def __str__(self):
        rev = self.source_sha[:12] if self.source_sha else self.source_ref
        return f"AdeSnapshot {rev} [{self.status}]"


class AdeEntry(models.Model):
    """
    One normalized upstream ADE record belonging to a snapshot.

    ``ade_id`` is the stable upstream identifier (``ADE3-01``, ``DLE-2026-00001``...) and is
    what Maieutic answers and overlay content will reference, so renames upstream do not
    break links. Likelihood checks have no upstream ID and are keyed by position.
    """

    class Kind(models.TextChoices):
        CATEGORY = 'CATEGORY', 'Category'
        SUBCATEGORY = 'SUBCATEGORY', 'Subcategory'
        LIKELIHOOD_CHECK = 'LIKELIHOOD_CHECK', 'Bug likelihood check'
        DLE = 'DLE', 'Detection logic example'
        ITW = 'ITW', 'In the wild'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    snapshot = models.ForeignKey(AdeSnapshot, on_delete=models.CASCADE, related_name='entries')
    entry_key = models.CharField(max_length=160, help_text="Stable key within a snapshot, e.g. 'SUBCATEGORY:ADE3-01'.")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    ade_id = models.CharField(max_length=40, blank=True, default='')
    parent_ade_id = models.CharField(max_length=16, blank=True, default='', help_text="Category ID for subcategories.")
    title = models.CharField(max_length=512, blank=True, default='')
    definition = models.TextField(blank=True, default='')
    related_ade = models.JSONField(default=list, blank=True)
    mitre_attack = models.JSONField(default=list, blank=True)
    logsource = models.JSONField(default=dict, blank=True)
    schema_version = models.CharField(max_length=16, blank=True, default='')
    source_path = models.CharField(max_length=512, blank=True, default='')
    source_hash = models.CharField(max_length=64, blank=True, default='')
    content = models.JSONField(default=dict, blank=True, help_text="Full parsed upstream record.")

    class Meta:
        ordering = ['kind', 'ade_id', 'entry_key']
        constraints = [
            models.UniqueConstraint(fields=['snapshot', 'entry_key'], name='unique_ade_entry_per_snapshot'),
        ]
        indexes = [
            models.Index(fields=['snapshot', 'kind'], name='pld_ade_ent_snap_kind_idx'),
            models.Index(fields=['ade_id'], name='pld_ade_ent_ade_id_idx'),
        ]
        verbose_name = "ADE Entry"
        verbose_name_plural = "ADE Entries"

    def __str__(self):
        return f"{self.ade_id or self.entry_key}: {self.title}"[:200]


class AdeImportJob(models.Model):
    """Tracks async ADE imports triggered from the Framework Updates page."""

    class Mode(models.TextChoices):
        REMOTE = 'REMOTE', 'Remote'
        LOCAL = 'LOCAL', 'Local'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_repo = models.URLField(
        max_length=512,
        default='https://github.com/Adversarial-Detection-Engineering/Adversarial-Detection-Engineering-Framework',
    )
    source_ref = models.CharField(max_length=128, default='main')
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.REMOTE)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    snapshot = models.ForeignKey(
        AdeSnapshot, null=True, blank=True, on_delete=models.SET_NULL, related_name='import_jobs',
    )
    summary = models.JSONField(default=dict, blank=True)
    log = models.TextField(blank=True, default='')
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ade_import_jobs',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "ADE Import Job"
        verbose_name_plural = "ADE Import Jobs"

    def __str__(self):
        return f"AdeImportJob {self.source_ref} [{self.status}] @ {self.created_at}"
