import uuid
import re
from django.db import models
from django.db.models import JSONField
from django.db import transaction
from organizations.models import Organization
from identity.models import CustomUser
from platform_data.models import MitreAttackTechnique, MitreIcsTechnique, MitreMobileTechnique
from taggit.managers import TaggableManager
from tags.models import TaggedPlaybook, TaggedGraph
"""
Avoid importing `DetectionRule` here to prevent circular imports with
`rules.models` which now references `PlaybookGraph`. Use a string reference
('rules.DetectionRule') on the ManyToManyField instead.
"""
from data_catalog.models import DataSource
from django.core.validators import MinValueValidator, MaxValueValidator
from core.rabbitmq import publish_event



class DetectionPlaybook(models.Model):
    class PlaybookStatus(models.TextChoices):
        IDEA = 'IDEA', 'Idea/Hypothesis'
        RESEARCH = 'RESEARCH', 'In Research'
        DEVELOPMENT = 'DEVELOPMENT', 'In Development'
        REVIEW = 'REVIEW', 'Peer Review'
        APPROVED = 'APPROVED', 'Approved'
        TESTING = 'TESTING', 'Testing/Validation'
        DEPLOYED = 'DEPLOYED', 'Deployed'
        TUNING = 'TUNING', 'Tuning/Maintenance'

    class PlaybookType(models.TextChoices):
        HUNT = 'HUNT', 'Hunt'
        DETECTION = 'DETECTION', 'Detection'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=PlaybookStatus.choices,
        default=PlaybookStatus.IDEA
    )
    playbook_type = models.CharField(
        max_length=20,
        choices=PlaybookType.choices,
        default=PlaybookType.HUNT
    )
    author = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='authored_playbooks')
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="playbooks"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    tags = TaggableManager(through=TaggedPlaybook, blank=True)


    detection_rules = models.ManyToManyField(
        'rules.DetectionRule',
        related_name="playbooks",
        blank=True
    )
    required_data_sources = models.ManyToManyField(
        DataSource,
        related_name="playbooks",
        blank=True
    )

    # --- SECTION 1: METADATA ---
    analytic_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Unique ID for the analytic (e.g., DE-2025-001)",
    )
    version = models.CharField(
        max_length=10,
        default="1.0",
        help_text="Semantic version of the analytic (e.g., 1.0)",
    )

    # --- ADD THIS FIELD ---
    is_shared = models.BooleanField(
        default=False,
        help_text="If true, this playbook is visible as a read-only template to all orgs in the same Entity.",
    )
    # --- END ADD ---

    # --- SECTION 2: DETECTION OVERVIEW ---
    hypothesis = models.TextField(
        blank=True,
        null=True,
        help_text="The testable question this hunt is designed to answer (for HUNT playbooks)",
    )

    # --- SECTION 3: ANALYTIC DETAILS ---
    class RobustnessLevel(models.IntegerChoices):
        LEVEL_1 = 1, "Level 1: Ephemeral (IP, Domain, Hash)"
        LEVEL_2 = 2, "Level 2: Implementation / Attacker-Controlled"
        LEVEL_3 = 3, "Level 3: System-Constrained Interaction (LOLBin)"
        LEVEL_4 = 4, "Level 4: Low-Variance Behaviors / Core Sometimes"
        LEVEL_5 = 5, "Level 5: Invariant Behaviors / Core to Technique"

    robustness_level = models.IntegerField(
        choices=RobustnessLevel.choices,
        blank=True,
        null=True,
        help_text="How easy is this detection to evade?",
    )

    class EventRobustness(models.TextChoices):
        APPLICATION = 'A', 'Application (A)'
        USER_MODE = 'U', 'User-Mode (U)'
        KERNEL_MODE = 'K', 'Kernel-Mode (K)'
        PAYLOAD = 'P', 'Protocol Payload (P)'
        HEADER = 'H', 'Protocol Header (H)'
        NONE = 'N', 'N/A'

    data_source_robustness = models.CharField(
        max_length=2,
        choices=EventRobustness.choices,
        blank=True,
        null=True,
        help_text="Where does the data come from? (e.g., K for Kernel-Mode)",
    )

    # --- SECTION 4: LOGIC & IMPLEMENTATION ---
    false_positive_rate = models.IntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Estimated FP rate on a 0-100% scale (for DETECTION playbooks)",
    )
    known_false_positives = models.TextField(
        blank=True,
        null=True,
        help_text="Known benign triggers to reduce noise (for DETECTION playbooks)",
    )
    exclusion_strategy = models.TextField(
        blank=True,
        null=True,
        help_text="Surgically precise exclusions (e.g., trusted signers)",
    )

    # --- SECTION 5: VALIDATION & RESPONSE ---
    testing_procedures = models.TextField(
        blank=True,
        null=True,
        help_text="Test cases and synonym tools to validate the detection",
    )
    triage_guidance = models.TextField(
        blank=True,
        null=True,
        help_text="Step-by-step instructions for T1 analysts (for DETECTION playbooks)",
    )

    # --- SECTION 6: AUTOMATION (SOAR) ---
    soar_enrichment = models.TextField(
        blank=True,
        null=True,
        help_text="Automated enrichment steps (e.g., Get-UserDetails)",
    )
    soar_triage = models.TextField(
        blank=True,
        null=True,
        help_text="Automated triage logic (e.g., IF user.is_vip -> THEN set_severity=High)",
    )
    soar_containment = models.TextField(
        blank=True,
        null=True,
        help_text="Automated containment steps (e.g., Isolate-Host)",
    )

    # --- SECTION 7: FRAMEWORK MAPPINGS (THE NEW M2M LINKS) ---
    mitre_attack_mappings = models.ManyToManyField(
        MitreAttackTechnique,
        related_name="playbooks",
        blank=True,
    )
    mitre_ics_mappings = models.ManyToManyField(
        MitreIcsTechnique,
        related_name="playbooks",
        blank=True,
    )
    mitre_mobile_mappings = models.ManyToManyField(
        MitreMobileTechnique,
        related_name="playbooks",
        blank=True,
    )

    # --- CAPABILITY ABSTRACTION (ADDED DAY 79) ---
    operational_path = models.TextField(
        blank=True,
        null=True,
        help_text="High-level operational path / phases for this detection/hunt",
    )
    function_call_graphs = models.TextField(
        blank=True,
        null=True,
        help_text="Relevant function/API call graph abstractions",
    )
    execution_modalities = models.TextField(
        blank=True,
        null=True,
        help_text="Execution modalities or behavioral variants addressed",
    )

    # --- HUNT-SPECIFIC DEEP TECHNICAL DETAILS ---
    technical_details = models.TextField(
        blank=True,
        null=True,
        help_text="Deep technical implementation notes (for HUNT playbooks)",
    )


    def __str__(self):
        return self.title


class CapabilityAbstraction(models.Model):
    class AbstractionLayer(models.TextChoices):
        TOOL = 'TOOL', 'Tool / Binary'
        API_EXPORT = 'API_EXPORT', 'API / Export'
        COM_IPC = 'COM_IPC', 'COM / IPC'
        REGISTRY_OBJECT = 'REGISTRY_OBJECT', 'Registry Object'
        PROTOCOL = 'PROTOCOL', 'Protocol'
        PROCESS_BEHAVIOR = 'PROCESS_BEHAVIOR', 'Process Behavior'
        NETWORK_BEHAVIOR = 'NETWORK_BEHAVIOR', 'Network Behavior'

    class SourceKind(models.TextChoices):
        SEEDED = 'SEEDED', 'Seeded Baseline'
        CUSTOM = 'CUSTOM', 'Custom'

    class ReviewStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        REVIEWED = 'REVIEWED', 'Reviewed'
        APPROVED = 'APPROVED', 'Approved'

    class Column(models.TextChoices):
        APPLICATION = 'A', 'Column A: Application'
        USER_MODE = 'U', 'Column U: User-Mode'
        KERNEL_MODE = 'K', 'Column K: Kernel-Mode'
        PAYLOAD_VISIBILITY = 'P', 'Column P: Payload Visibility'
        HEADER_VISIBILITY = 'H', 'Column H: Header Visibility'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    technique = models.ForeignKey(
        MitreAttackTechnique,
        on_delete=models.CASCADE,
        related_name='capability_abstractions',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='capability_abstractions',
        help_text="Null means this is a shared baseline entry available to all organizations.",
    )
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_capability_abstractions',
    )
    updated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_capability_abstractions',
    )
    abstraction_layer = models.CharField(max_length=32, choices=AbstractionLayer.choices)
    component_artifact = models.CharField(max_length=255)
    adversary_purpose = models.TextField(blank=True)
    common_evasions = models.TextField(blank=True)
    expected_observables = models.TextField(blank=True)
    applicable_telemetry = models.TextField(blank=True)
    detection_value = models.TextField(blank=True)
    robustness_level = models.IntegerField(
        default=0,
        help_text="Suggested robustness tradeoff for this abstraction (1-5, aligned to the workbench badge scale).",
    )
    column = models.CharField(
        max_length=1,
        choices=Column.choices,
        blank=True,
        default='',
    )
    source_kind = models.CharField(
        max_length=16,
        choices=SourceKind.choices,
        default=SourceKind.CUSTOM,
    )
    review_status = models.CharField(
        max_length=16,
        choices=ReviewStatus.choices,
        default=ReviewStatus.DRAFT,
    )
    is_baseline = models.BooleanField(
        default=False,
        help_text="True when this entry is part of the shared seeded baseline library.",
    )
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['technique__technique_id', 'abstraction_layer', 'component_artifact']
        constraints = [
            models.UniqueConstraint(
                fields=['technique', 'organization', 'abstraction_layer', 'component_artifact'],
                name='unique_capability_abstraction_per_scope',
            )
        ]

    @property
    def is_shared_baseline(self) -> bool:
        return self.organization_id is None

    def __str__(self):
        return f"{self.technique.technique_id}::{self.abstraction_layer}::{self.component_artifact}"


class WorkbenchIdCounter(models.Model):
    """
    Global singleton counter for workbench IDs in the form DE000001, DE000002, ...
    """
    singleton_key = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    next_value = models.PositiveIntegerField(default=1)
    workbench_visibility_policy = models.JSONField(
        default=dict,
        blank=True,
        help_text="System-level workbench visibility policy overrides.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Workbench ID Counter"
        verbose_name_plural = "Workbench ID Counter"

    @classmethod
    def consume_next_custom_id(cls) -> str:
        with transaction.atomic():
            counter, _ = cls.objects.select_for_update().get_or_create(
                singleton_key=1,
                defaults={"next_value": 1},
            )
            current_value = counter.next_value
            counter.next_value = current_value + 1
            counter.save(update_fields=["next_value", "updated_at"])
        return f"DE{current_value:06d}"


class PlaybookGraph(models.Model):
    """
    The 'Playbook' Container.
    Holds the Visuals (Graph), the Strategy (MITRE), and the Context (Deep Dive).

    OpenTIDE Integration
    --------------------
    When committing to an InitTide repository, the workbench fields are compiled
    into three structured OpenTIDE objects:

    - **TVM** (Threat Vector Model): Captures the adversary behaviour/attack path.
      Sourced from ``mitre_technique``, ``technical_context``, ``blind_spots``,
      and ``triage_guidance``.  Stored in ``Objects/Threat Vectors/<id>.yaml``.

    - **DOM** (Detection Objective Model): A platform-agnostic detection blueprint
      linking the TVM to the MDR.  Derived from ``goal``, ``default_severity``,
      ``triage_guidance``, ``false_positives``, ``linked_rules``, and
      ``technical_context`` (used to infer ``signals``, ``priority``, and
      ``composition``).  Stored in ``Objects/Detection Objectives/<id>.yaml``.

    - **MDR** (Managed Detection Rule): Contains the actual platform-specific
      detection queries sourced from linked ``DetectionRule`` objects
      (KQL → Defender for Endpoint, SPL → Splunk, SIGMA, WAZUH, Elastic).
      Stored in ``Objects/Detection Rules/<id>.yaml``.

    An optional **BDR** (Business Detection Rule) is generated when the detection
    is classified as business-driven (e.g. compliance/GDPR scenarios).

    See ``backend/playbooks/utils/opentide_compiler.py`` for the compilation
    logic and ``backend/playbooks/git_client.py`` for the InitTide commit flow.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    author = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, default='IDEA')
    
    # Visual Artifact
    png_snapshot = models.ImageField(upload_to='playbook_graphs/', blank=True, null=True)
    
    # --- PART 1: DETECTION STRATEGY (Global for this Playbook) ---
    mitre_technique = models.ForeignKey(MitreAttackTechnique, on_delete=models.SET_NULL, null=True, blank=True)
    
    # D3FEND defensive techniques
    d3fend_techniques = models.ManyToManyField(
        'platform_data.D3fendDefensiveTechnique',
        related_name='implementing_playbooks',
        blank=True,
        help_text="D3FEND techniques this detection implements"
    )
    
    # Stores the selected MITRE Strategy/Analytic details
    # { "strategy_id": "...", "analytic_id": "...", "robustness": 4 }
    selected_strategy = JSONField(default=dict, blank=True)
    
    # The actual detection logic (Sigma/Pseudo-code)
    detection_rule = models.TextField(blank=True, help_text="Raw Sigma/Logic")

    # --- PART 2: DEEP DIVE (Human Context) ---
    goal = models.TextField(blank=True)
    technical_context = models.TextField(blank=True)
    blind_spots = models.TextField(blank=True)
    triage_guidance = models.TextField(blank=True)
    false_positives = models.TextField(blank=True)
    response_playbook = models.TextField(blank=True)

    # --- TESTING GUIDANCE ---
    test_scenario = models.TextField(
        blank=True,
        help_text="Markdown description of how to simulate this attack."
    )
    test_expected_output = models.TextField(
        blank=True,
        help_text="Example log event or artifact created by the test."
    )

    # --- DEPLOYMENT METADATA ---
    # Where should this rule live in the Git Repo?
    target_file_path = models.CharField(
        max_length=512, 
        blank=True, 
        help_text="e.g. rules/windows/process_creation/proc_mimikatz.yml"
    )
    
    # Status of the sync
    git_status = models.CharField(
        max_length=20, 
        choices=[('DRAFT', 'Draft'), ('SYNCED', 'Synced'), ('MODIFIED', 'Modified')], 
        default='DRAFT'
    )
    
    # Store the last commit hash to know if DB is ahead of Git
    last_commit_hash = models.CharField(max_length=40, blank=True)

    # --- METADATA ---
    # Stable human-readable ID (global sequence): DE000001, DE000002, ...
    custom_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    version = models.IntegerField(default=1)
    minor_version = models.IntegerField(default=0)
    
    # --- VALUATION (Summiting Pyramid) ---
    
    # Logic Level (1-5)
    robustness_level = models.IntegerField(default=0, help_text="1=Ephemeral, 2=Tool, 3=LOLBin, 4=Behavior, 5=Invariant")
    
    # Event Robustness (Host/Network Code)
    SOURCE_TYPES = [
        ('K', 'Kernel-Mode (K)'),
        ('U', 'User-Mode (U)'),
        ('A', 'Application (A)'),
        ('H', 'Protocol Header (H)'),
        ('P', 'Protocol Payload (P)'),
    ]
    data_source_robustness = models.CharField(max_length=5, choices=SOURCE_TYPES, blank=True, default='')
    
    # --- MAIEUTIC ENGINE FIELDS ---
    # Data source maturity from Maieutic Engine robustness recommendation
    DATA_SOURCE_MATURITY_CHOICES = [
        ('APPLICATION', 'Application'),
        ('USER_MODE', 'User-Mode'),
        ('KERNEL_MODE', 'Kernel-Mode'),
    ]
    data_source_maturity = models.CharField(
        max_length=20, 
        null=True, 
        blank=True,
        choices=DATA_SOURCE_MATURITY_CHOICES,
        help_text="Data source maturity level from Maieutic Engine"
    )
    
    # Maieutic Engine conversation log for audit trail
    conversation_history = JSONField(
        default=list, 
        blank=True,
        help_text="Maieutic Engine conversation log for audit trail"
    )
    selected_capability_abstractions = models.ManyToManyField(
        CapabilityAbstraction,
        related_name='playbook_graphs',
        blank=True,
        help_text="Capability abstractions selected as grounding knowledge for this workbench.",
    )
    detection_focus_layer = models.CharField(
        max_length=32,
        choices=CapabilityAbstraction.AbstractionLayer.choices,
        blank=True,
        default='',
        help_text="The capability abstraction layer the engineer wants AI generation to prioritize.",
    )

    # --- OPENTIDE INTEGRATION ---
    # TLP classification for information sharing (WikiTide v2.1)
    tlp_classification = models.CharField(
        max_length=20,
        choices=[
            ('CLEAR', 'TLP:CLEAR - Public disclosure'),
            ('GREEN', 'TLP:GREEN - Community sharing'),
            ('AMBER', 'TLP:AMBER - Limited disclosure'),
            ('AMBER+STRICT', 'TLP:AMBER+STRICT - Organization only'),
            ('RED', 'TLP:RED - Personal for named recipients'),
        ],
        default='AMBER',
        help_text='Traffic Light Protocol classification for information sharing',
    )

    # Public references (URLs, research papers, blog posts)
    public_references = models.JSONField(
        default=list,
        blank=True,
        help_text='Public references (URLs, research papers, blog posts)',
    )

    # Internal references (tickets, case IDs, internal docs)
    internal_references = models.JSONField(
        default=list,
        blank=True,
        help_text='Internal references (tickets, case IDs, internal docs)',
    )

    # Known threat actors using this TTP
    threat_actors = models.JSONField(
        default=list,
        blank=True,
        help_text='Known threat actors using this TTP (structured data)',
    )

    # Manual threat surface overrides (hierarchical taxonomy: OS::Windows, Cloud::Azure, …)
    # When set, these values are used verbatim in the TVM output; the auto-detected surfaces
    # from technical_context are merged in as additional entries.
    threat_surface = models.JSONField(
        default=list,
        blank=True,
        help_text='Manually specified threat surface categories (e.g. OS::Windows, Cloud::Azure)',
    )

    # Store OpenTide multi-platform YAML structure
    opentide_yaml = models.JSONField(
        blank=True,
        null=True,
        help_text="OpenTide multi-platform YAML structure"
    )

    # Track which platforms are configured
    configured_platforms = models.JSONField(
        default=list,
        help_text="List of configured platforms: ['kql', 'spl', 'sigma', 'wazuh']"
    )

    # AI-generated threat metadata cache for OpenTIDE TVM/DOM enrichment.
    # Cached so repeated commits produce deterministic YAML without extra LLM calls.
    opentide_ai_enrichment = models.JSONField(
        blank=True,
        null=True,
        help_text=(
            "Cached AI-enriched threat fields for OpenTIDE export "
            "(terrain, leverage, impact, viability, description)."
        ),
    )

    # --- OPENTIDE MDR TESTING METADATA ---
    test_validation_status = models.CharField(
        max_length=20,
        choices=[
            ('PASSED', 'Passed'),
            ('FAILED', 'Failed'),
            ('NOT_TESTED', 'Not Tested'),
        ],
        default='NOT_TESTED',
        help_text="Validation status from CI/CD test pipeline"
    )

    test_results = models.JSONField(
        blank=True,
        null=True,
        help_text="Test execution results and validation outputs"
    )

    last_tested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of last test execution"
    )

    # --- OPENTIDE MDR TUNING PARAMETERS ---
    time_window = models.CharField(
        max_length=20,
        blank=True,
        help_text="Query time window (e.g., '5m', '1h', '24h')"
    )

    alert_threshold = models.IntegerField(
        null=True,
        blank=True,
        help_text="Alert threshold value"
    )

    threshold_operator = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ('greater_than', 'Greater Than'),
            ('less_than', 'Less Than'),
            ('equals', 'Equals'),
        ],
        default='greater_than'
    )

    aggregation_field = models.CharField(
        max_length=100,
        blank=True,
        help_text="Field to aggregate by (e.g., 'user', 'host')"
    )

    aggregation_function = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ('count', 'Count'),
            ('sum', 'Sum'),
            ('avg', 'Average'),
            ('max', 'Maximum'),
        ],
        default='count'
    )

    suppression_window = models.CharField(
        max_length=20,
        blank=True,
        help_text="Alert suppression window (e.g., '1h')"
    )

    # Standard Metadata
    is_shared = models.BooleanField(default=False)
    allow_remote_pull = models.BooleanField(
        default=False,
        help_text='If enabled, this workbench can be exported to trusted remote HEFAISTOS peers.',
    )
    notes = models.TextField(blank=True, null=True)
    playbooks = models.ManyToManyField(DetectionPlaybook, related_name="graphs", blank=True)
    tags = TaggableManager(through=TaggedGraph, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- IMPORT PROVENANCE ---
    # Populated by hef_import_worker when a Workbench is created from an OpenTIDE HEF bundle.
    imported_from_repo = models.CharField(
        max_length=512,
        blank=True,
        default='',
        help_text='GitHub repo (owner/name) this workbench was imported from, e.g. org/rules-prod',
    )
    imported_from_commit_sha = models.CharField(
        max_length=40,
        blank=True,
        default='',
        help_text='Git commit SHA at which the HEF bundle was read during import',
    )
    imported_from_path = models.CharField(
        max_length=512,
        blank=True,
        default='',
        help_text='Path of the HEF bundle within the repository (the MDR YAML path)',
    )
    imported_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of the import operation',
    )
    imported_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='imported_workbenches',
        help_text='User who triggered the HEF import job',
    )

    # --- SOAR CONFIGURATION ---
    # 1. Trigger & Severity
    alert_trigger = models.TextField(
        blank=True, 
        default="Triggered when the Detection Logic condition is met."
    )
    default_severity = models.CharField(
        max_length=20, 
        choices=[('LOW', 'Low'), ('MEDIUM', 'Medium'), ('HIGH', 'High'), ('CRITICAL', 'Critical')],
        default='MEDIUM'
    )
    
    # 2. Enrichment Steps (List of { action, input, output, description })
    enrichment_steps = models.JSONField(default=list, blank=True)
    
    # 3. Containment Steps (List of { action, critical: bool, description })
    containment_steps = models.JSONField(default=list, blank=True)
    
    # 4. Notification Steps (List of { channel, recipient, template })
    notification_steps = models.JSONField(default=list, blank=True)

    # 5. Downstream Correlation Requirements
    downstream_correlation_requirements = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Temporal/join logic for multi-event correlation detections. "
            "Structure: { correlationScope, temporalLogic, joinKeys, stateManagement, falsePositiveMitigation }"
        )
    )

    # --- TELEMETRY TAGGING (Milestone 1: derivation only, no org-health verification) ---
    # Derived list of telemetry the detection is expected to depend on, generated as a
    # byproduct of technique + narrative + rule analysis (never a precondition for
    # authoring). Each entry: { source, component, fields, rationale, origin, status }.
    # `status` is always "unverified" in this milestone: entries are derived from MITRE
    # reference vocabulary (MitreDataComponent / ChokepointEntry / DataSourceField), not
    # confirmed against any real organization environment. See
    # Docs/TELEMETRY_TAGGING.md for the full design and gate rules.
    telemetry_requirements = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "AI-derived/edited telemetry requirement tags for this Workbench object. "
            "Always unverified reference-vocabulary hypotheses in this milestone; see "
            "Docs/TELEMETRY_TAGGING.md."
        ),
    )
    telemetry_requirements_generated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the last successful telemetry-tag derivation run.",
    )

    # --- AUTOMATION HELPERS ---

    # --- TELEMETRY TAGGING GATE ---
    # Required-field gate documented in Docs/TELEMETRY_TAGGING.md. Kept as an instance
    # method (rather than only frontend logic) so the GraphQL mutation can enforce the
    # hard block server-side regardless of what the UI does.
    def telemetry_tagging_missing_fields(self) -> list:
        """
        Return the list of human-readable required-field labels that are still
        empty/unset for this Workbench object, per the telemetry-tagging gate:

        1. ATT&CK TTP           -> mitre_technique
        2. Strategic Goal       -> goal
        3. Technical Context    -> technical_context
        4. Detection Rule       -> detection_rule
        5. Threat Surface Taxonomy -> threat_surface

        Field #5 lives in the otherwise-optional "Part 4: SOAR Configuration"
        section, but is a hard precondition for telemetry-tag derivation
        regardless of that section's visibility state for the current user.
        """
        missing = []
        if self.mitre_technique_id is None:
            missing.append("ATT&CK TTP")
        if not (self.goal or "").strip():
            missing.append("Strategic Goal")
        if not (self.technical_context or "").strip():
            missing.append("Technical Context")
        if not (self.detection_rule or "").strip():
            missing.append("Detection Rule")
        if not self.threat_surface:
            missing.append("Threat Surface Taxonomy")
        return missing

    def telemetry_tagging_gate_passed(self) -> bool:
        return len(self.telemetry_tagging_missing_fields()) == 0

    # --- OPENTIDE METADATA HELPERS ---
    def compile_opentide_metadata(self) -> dict:
        """
        Compile OpenTide metadata from workbench fields.

        Returns:
            dict: OpenTide metadata structure
        """
        from playbooks.utils.opentide_compiler import compile_opentide_metadata
        return compile_opentide_metadata(self)

    def auto_update_opentide_yaml(self):
        """
        Auto-update opentide_yaml with latest metadata.

        Preserves existing platform queries; only refreshes the metadata section.
        """
        from playbooks.utils.opentide_compiler import merge_metadata_with_platforms

        existing_platforms = {}
        if self.opentide_yaml and isinstance(self.opentide_yaml, dict):
            existing_platforms = self.opentide_yaml.get('platforms', {})

        self.opentide_yaml = merge_metadata_with_platforms(self, existing_platforms)

        if existing_platforms:
            self.configured_platforms = list(existing_platforms.keys())

    @staticmethod
    def strip_custom_id_prefix(title: str | None) -> str:
        """
        Remove one or more leading DE-ID-style prefixes from a title.
        Supports both legacy and current formats, for example:
        [DE000001], [DE-T1059-001], [de000123], ...
        """
        text = (title or "").strip()
        while True:
            updated = re.sub(r'^\s*\[\s*DE[^\]]*\]\s*', '', text, flags=re.IGNORECASE)
            if updated == text:
                break
            text = updated
        return text

    @classmethod
    def compose_title_with_custom_id(cls, title: str | None, custom_id: str | None) -> str:
        """
        Force title prefix format: [DE000001]suffix (no added space).
        """
        base = cls.strip_custom_id_prefix(title)
        if not custom_id:
            return base[:255]
        return f"[{custom_id}]{base}"[:255]

    def save(self, *args, **kwargs):
        # Auto-generate ID on first save when missing.
        if not self.custom_id:
            self.custom_id = WorkbenchIdCounter.consume_next_custom_id()
        # Auto-refresh OpenTide metadata whenever opentide_yaml is already set.
        # auto_update_opentide_yaml() only modifies instance attributes in memory;
        # the actual DB persist happens in the super().save() call below.
        # No recursion risk: super().save() is Django's Model.save(), not this override.
        if self.opentide_yaml:
            self.auto_update_opentide_yaml()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class L1PortalEntry(models.Model):
    """
    Read-only L1-facing snapshot materialized from a deployed Workbench.

    A single Workbench has at most one L1 portal entry. The share token is
    stable so downstream automation can keep using the same URL.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    graph = models.OneToOneField(
        PlaybookGraph,
        on_delete=models.CASCADE,
        related_name='l1_portal_entry',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='l1_portal_entries',
    )
    title = models.CharField(max_length=300)
    url_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    response_playbook = models.TextField(blank=True, default='')
    known_false_positives = models.TextField(blank=True, default='')
    blind_spots_coverage_gaps = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['organization', 'updated_at']),
            models.Index(fields=['url_token']),
        ]

    def __str__(self):
        return self.title


class ActivityLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    playbook = models.ForeignKey(PlaybookGraph, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50) # "CREATED", "UPDATED", "APPROVED"
    details = models.TextField(blank=True) # "Changed severity to HIGH"
    timestamp = models.DateTimeField(auto_now_add=True)

class Task(models.Model):
    class TaskStatus(models.TextChoices):
        TODO = 'TODO', 'To-Do'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        DONE = 'DONE', 'Done'

    # --- UPDATE THIS FOREIGN KEY ---
    # Old: playbook = models.ForeignKey(DetectionPlaybook, ...)
    # New: Point to the GRAPH
    playbook = models.ForeignKey(
        PlaybookGraph, 
        on_delete=models.CASCADE, 
        related_name="tasks"
    )
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=TaskStatus.choices,
        default=TaskStatus.TODO
    )
    assignee = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class PlaybookNode(models.Model):
    """
    Visual-only node. No more detection logic here.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    graph = models.ForeignKey(PlaybookGraph, on_delete=models.CASCADE, related_name="nodes")
    
    # Visuals
    layer_name = models.CharField(max_length=100, default="New Node")
    position_x = models.FloatField(default=50)
    position_y = models.FloatField(default=50)
    color = models.CharField(max_length=20, default="default", help_text="Node color: default, blue, green, yellow, red")
    
    # ATT&CK technique mappings specific to this node (optional)
    mitre_attack_mappings = models.ManyToManyField(
        MitreAttackTechnique,
        related_name="nodes",
        blank=True,
    )
    
    # D3FEND technique mappings specific to this node (optional)
    d3fend_mappings = models.ManyToManyField(
        'platform_data.D3fendDefensiveTechnique',
        related_name='nodes',
        blank=True
    )

    # Just for UI state (e.g. "is this node collapsed?")
    ui_metadata = JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.layer_name} ({self.graph.title})"

class PlaybookEdge(models.Model):
    """
    A connection between two nodes in a PlaybookGraph.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    graph = models.ForeignKey(PlaybookGraph, on_delete=models.CASCADE, related_name="edges")
    source_node = models.ForeignKey(PlaybookNode, on_delete=models.CASCADE, related_name="source_edges")
    target_node = models.ForeignKey(PlaybookNode, on_delete=models.CASCADE, related_name="target_edges")
    def __str__(self):
        return f"{self.source_node.layer_name} -> {self.target_node.layer_name}"

class PlaybookComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    playbook = models.ForeignKey(PlaybookGraph, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at'] # Oldest first (Chat style)

    def __str__(self):
        return f"{self.user.username}: {self.message[:20]}"

class ReviewRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    playbook = models.ForeignKey(PlaybookGraph, on_delete=models.CASCADE, related_name='review_requests')
    
    requester = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='requested_reviews')
    reviewer = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_reviews')
    
    status = models.CharField(
        max_length=20, 
        choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')],
        default='PENDING'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            # TRIGGER RABBITMQ: Notify Reviewers
            publish_event('playbook.review_requested', {
                'playbook_id': str(self.playbook.id),
                'title': self.playbook.title,
                'requester': self.requester.username if self.requester else 'Unknown',
                'request_id': str(self.id)
            })

    def __str__(self):
        return f"Review {self.playbook.title} ({self.status})"

class ReviewComment(models.Model):
    """
    Formal comments attached to a Review Request (e.g., 'Fix the logic in line 4').
    Distinct from the casual Chat.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review_request = models.ForeignKey(ReviewRequest, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # TRIGGER RABBITMQ: Notify Requester of feedback
        publish_event('playbook.review_commented', {
            'playbook_id': str(self.review_request.playbook.id),
            'comment_snippet': self.text[:50] + "...",
            'user': self.user.username if self.user else 'System'
        })


class OpentidePreviewTask(models.Model):
    """Async task for OpenTIDE metadata preview via RabbitMQ (optional AI enrichment)."""

    class TaskStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    playbook = models.ForeignKey(
        PlaybookGraph,
        on_delete=models.CASCADE,
        related_name='opentide_preview_tasks',
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='opentide_preview_tasks',
    )
    status = models.CharField(
        max_length=20,
        choices=TaskStatus.choices,
        default=TaskStatus.PENDING,
    )
    use_ai_enrichment = models.BooleanField(default=True)
    force_bdr_generation = models.BooleanField(default=False)
    result_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"OpentidePreviewTask({self.id}, {self.status})"


class MveDraft(models.Model):
    """Machina Velocity Engine draft graph persisted independently of Workbench graphs."""

    class DraftStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        MODELED = 'MODELED', 'Modeled'
        GENERATION_READY = 'GENERATION_READY', 'Generation Ready'
        VALIDATED = 'VALIDATED', 'Validated'
        EXPORTED = 'EXPORTED', 'Exported'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='mve_drafts',
    )
    author = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mve_drafts',
    )
    name = models.CharField(max_length=255, default='New Velocity Chain')
    status = models.CharField(max_length=20, choices=DraftStatus.choices, default=DraftStatus.DRAFT)
    anchor_entity = models.CharField(max_length=255, default='host.hostname')
    max_total_span_ms = models.PositiveIntegerField(default=800)
    analytic_family = models.CharField(max_length=64, blank=True, null=True)
    primary_methodology = models.CharField(max_length=64, default='volumetric_de')
    behavior_object = models.JSONField(default=dict, blank=True)
    dimensions = models.JSONField(default=dict, blank=True)
    measurement_model = models.JSONField(default=dict, blank=True)
    time_window_logic = models.JSONField(default=dict, blank=True)
    baseline_strategy = models.JSONField(default=dict, blank=True)
    context_risk = models.JSONField(default=dict, blank=True)
    generation_profile = models.JSONField(default=dict, blank=True)
    downstream_handoff = models.JSONField(default=dict, blank=True)
    is_advops_validated = models.BooleanField(default=False)
    validation_summary = models.JSONField(default=dict, blank=True)
    last_validated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['organization', 'updated_at']),
        ]

    def __str__(self):
        return f"{self.name} ({self.status})"


class MveNode(models.Model):
    class NodeType(models.TextChoices):
        EVENT = 'EVENT', 'Event'
        RULE = 'RULE', 'Rule'
        FEATURE = 'FEATURE', 'Feature'
        BASELINE = 'BASELINE', 'Baseline'
        CONTEXT = 'CONTEXT', 'Context'
        DECEPTION = 'DECEPTION', 'Deception'
        DECISION = 'DECISION', 'Decision'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    draft = models.ForeignKey(
        MveDraft,
        on_delete=models.CASCADE,
        related_name='nodes',
    )
    step_order = models.PositiveIntegerField(default=1)
    node_type = models.CharField(max_length=10, choices=NodeType.choices)
    label = models.CharField(max_length=255, blank=True, default='')
    data_source = models.ForeignKey(
        DataSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mve_nodes',
    )
    detection_rule = models.ForeignKey(
        'rules.DetectionRule',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mve_nodes',
    )
    capability_abstraction = models.ForeignKey(
        CapabilityAbstraction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mve_nodes',
    )
    tactic_ref = models.CharField(max_length=20, blank=True, default='')
    technique_ref = models.CharField(max_length=20, blank=True, default='')
    criteria = models.JSONField(default=dict, blank=True)
    node_config = models.JSONField(default=dict, blank=True)
    position_x = models.FloatField(default=120)
    position_y = models.FloatField(default=120)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['step_order', 'created_at']
        indexes = [
            models.Index(fields=['draft', 'step_order']),
            models.Index(fields=['draft', 'node_type']),
        ]

    def __str__(self):
        return f"{self.draft_id}:{self.node_type}:{self.step_order}"


class MveEdge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    draft = models.ForeignKey(
        MveDraft,
        on_delete=models.CASCADE,
        related_name='edges',
    )
    source_node = models.ForeignKey(
        MveNode,
        on_delete=models.CASCADE,
        related_name='outgoing_edges',
    )
    target_node = models.ForeignKey(
        MveNode,
        on_delete=models.CASCADE,
        related_name='incoming_edges',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['draft', 'source_node', 'target_node'],
                name='uniq_mve_edge_per_draft',
            ),
        ]
        indexes = [
            models.Index(fields=['draft']),
        ]

    def __str__(self):
        return f"{self.source_node_id}->{self.target_node_id}"


class MveValidationRun(models.Model):
    class RunStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        RUNNING = 'RUNNING', 'Running'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    draft = models.ForeignKey(
        MveDraft,
        on_delete=models.CASCADE,
        related_name='validation_runs',
    )
    requested_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mve_validation_runs',
    )
    status = models.CharField(max_length=20, choices=RunStatus.choices, default=RunStatus.PENDING)
    result_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['draft', 'created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"MveValidationRun({self.id}, {self.status})"
