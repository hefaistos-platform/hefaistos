import graphene
import logging
import re
from datetime import timedelta
from typing import Dict, List, Set
from django.core.exceptions import ValidationError
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from graphene_django import DjangoObjectType
from graphql import GraphQLError
from ai_assistant.models import OrgAISettings, SharedAIProfile
from .models import (
    Organization,
    OrganizationBillingProfile,
    OrganizationManagerAccess,
    Entity,
    MISPInstance,
    MISP_INSTANCE_LIMIT,
    SharedSmtpProfile,
    OrganizationSmtpSettings,
    get_effective_smtp_for_organization,
    PlatformCredential,
    OpenTidePublishProfile,
    OpenTideHefPublishJob,
    OpenTideHefImportJob,
    DacDeploymentConfig,
    OrganizationAITaskConfig,
    OrganizationAITaskRun,
    HefaistosInstanceIdentity,
    HefaistosRemotePeer,
    HefaistosInboundShareKey,
    HefaistosPullJob,
)
from .billing import create_addon_checkout_session, stripe_is_configured
from .sharing import (
    build_key_hint,
    compute_next_auto_pull_at,
    effective_required_tags,
    generate_raw_share_key,
    get_or_create_instance_identity,
    hash_api_key,
    normalize_auto_pull_schedule,
    normalize_required_tags,
    normalize_scope,
    pull_from_remote_peer,
)
from .ai_tasks import (
    ensure_org_task_configs,
    get_ai_task_definition,
    get_or_create_task_config,
    run_task_now,
    update_task_config,
)
from identity.decorators import role_required, Roles
from identity.models import CustomUser
from identity.schema import UserType
from rules.deployers import PLATFORM_DEPLOYER_MAP

logger = logging.getLogger(__name__)
_UNSET = object()

VALID_DEPLOYMENT_PLATFORMS = {'defender', 'sentinel', 'splunk', 'qradar', 'wazuh'}
PLATFORM_DISPLAY_LABELS = dict(PlatformCredential.PLATFORM_CHOICES)
KQL_TARGET_POLICIES = {'defender', 'sentinel', 'both'}
PLATFORM_VALUE_MAP = {
    'kql': 'defender',
    'spl': 'splunk',
    'wazuh': 'wazuh',
    'qradar': 'qradar',
    # These do not map to a single deployment endpoint.
    'eql': None,
    'elastic': None,
}


def normalize_deployment_platforms(
    platforms: List[str],
    *,
    kql_target_policy: str = 'defender',
) -> tuple[List[str], List[str]]:
    mapped: List[str] = []
    dropped: List[str] = []
    normalized_kql_policy = str(kql_target_policy or 'defender').strip().lower()
    if normalized_kql_policy not in KQL_TARGET_POLICIES:
        normalized_kql_policy = 'defender'

    for platform in platforms or []:
        if not platform:
            continue
        value = str(platform).strip().lower()
        if not value:
            continue

        if value in VALID_DEPLOYMENT_PLATFORMS:
            mapped.append(value)
            continue

        if value == 'kql':
            if normalized_kql_policy == 'both':
                mapped.extend(['defender', 'sentinel'])
            elif normalized_kql_policy == 'sentinel':
                mapped.append('sentinel')
            else:
                mapped.append('defender')
            continue

        if value in PLATFORM_VALUE_MAP and PLATFORM_VALUE_MAP[value]:
            mapped.append(PLATFORM_VALUE_MAP[value])
            continue

        dropped.append(value)

    return list(dict.fromkeys(mapped)), list(dict.fromkeys(dropped))


class EntityType(DjangoObjectType):
    """GraphQL type for Entity (holding company/MSSP)."""
    organization_count = graphene.Int()
    
    class Meta:
        model = Entity
        fields = ("id", "name", "created_at")
    
    def resolve_organization_count(self, info):
        return self.organizations.count()


class OrganizationType(DjangoObjectType):
    # Expose members with optional exclusion of a specific user (e.g., the author)
    members = graphene.List(UserType, exclude_author_id=graphene.ID())
    member_count = graphene.Int()
    entity = graphene.Field(EntityType)
    smtp_shared_enabled = graphene.Boolean()
    ai_shared_enabled = graphene.Boolean()
    workbench_visibility_policy = graphene.JSONString()

    class Meta:
        model = Organization
        fields = ("id", "name", "max_users", "created_at", "updated_at", "entity")

    def resolve_members(self, info, exclude_author_id=None):
        qs = CustomUser.objects.filter(organization=self)
        if exclude_author_id:
            qs = qs.exclude(pk=exclude_author_id)
        return qs
    
    def resolve_member_count(self, info):
        return CustomUser.objects.filter(organization=self).count()

    def resolve_smtp_shared_enabled(self, info):
        try:
            settings_obj = self.smtp_settings
        except OrganizationSmtpSettings.DoesNotExist:
            return False
        return bool(getattr(settings_obj, 'enforce_shared', False))

    def resolve_ai_shared_enabled(self, info):
        try:
            settings_obj = self.ai_settings
        except OrgAISettings.DoesNotExist:
            return False
        return bool(getattr(settings_obj, 'shared_profile_locked', False))

    def resolve_workbench_visibility_policy(self, info):
        value = getattr(self, 'workbench_visibility_policy', None)
        return value if isinstance(value, dict) else {}


class OrganizationBillingProfileType(graphene.ObjectType):
    organization_id = graphene.UUID()
    stripe_customer_id = graphene.String()
    stripe_subscription_id = graphene.String()
    included_users = graphene.Int()
    included_organizations = graphene.Int()
    extra_users = graphene.Int()
    extra_organizations = graphene.Int()
    max_users = graphene.Int()
    max_organizations = graphene.Int()
    is_stripe_configured = graphene.Boolean()
    updated_at = graphene.DateTime()


class BillingCheckoutSessionType(graphene.ObjectType):
    checkout_url = graphene.String(required=True)
    session_id = graphene.String(required=True)


class OrganizationManagerAccessType(graphene.ObjectType):
    user_id = graphene.UUID()
    username = graphene.String()
    organization_id = graphene.UUID()
    organization_name = graphene.String()
    access_role = graphene.String()

    def resolve_user_id(self, info):
        return self.user_id

    def resolve_username(self, info):
        return self.user.username if self.user_id else None

    def resolve_organization_id(self, info):
        return self.organization_id

    def resolve_organization_name(self, info):
        return self.organization.name if self.organization_id else None


class MISPInstanceType(DjangoObjectType):
    """GraphQL type for a MISP instance."""

    class Meta:
        model = MISPInstance
        fields = (
            "id",
            "name",
            "url",
            "verify_ssl",
            "auto_pull_enabled",
            "auto_pull_schedule",
            "auto_pull_tag",
            "next_auto_pull_at",
            "created_at",
            "updated_at",
        )

    auth_key_hint = graphene.String(description="Last 4 chars of auth key (masked)")

    def resolve_auth_key_hint(self, info):
        if self.auth_key and len(self.auth_key) >= 4:
            return "****" + self.auth_key[-4:]
        return "****"


# ---------------------------------------------------------------------------
# Platform Credential GraphQL types (must be before Query class)
# ---------------------------------------------------------------------------

class PlatformCredentialType(graphene.ObjectType):
    """GraphQL type for a platform credential entry (credentials are never exposed)."""
    id = graphene.UUID()
    platform = graphene.String()
    platform_display = graphene.String()
    profile_name = graphene.String()
    is_default = graphene.Boolean()
    enabled = graphene.Boolean()
    has_credentials = graphene.Boolean()
    last_tested = graphene.DateTime()
    test_status = graphene.Boolean()
    test_message = graphene.String()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()

    def resolve_platform_display(self, info):
        return dict(PlatformCredential.PLATFORM_CHOICES).get(self.platform, self.platform)

    def resolve_has_credentials(self, info):
        return bool(self._credentials_json)


class OpenTidePublishProfileType(graphene.ObjectType):
    id = graphene.UUID()
    name = graphene.String()
    repository_id = graphene.UUID()
    repository_name = graphene.String()
    repository_url = graphene.String()
    branch = graphene.String()
    target_folder = graphene.String()
    push_platform_rules = graphene.Boolean()
    enabled_platforms = graphene.List(graphene.String)
    use_graph_configured_platforms = graphene.Boolean()
    kql_target_policy = graphene.String()
    enabled = graphene.Boolean()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()

    def resolve_repository_id(self, info):
        return self.repository_id

    def resolve_repository_name(self, info):
        return self.repository.name if self.repository else None

    def resolve_repository_url(self, info):
        return self.repository.git_url if self.repository else None

    def resolve_enabled_platforms(self, info):
        return self.enabled_platforms or []


class OpenTideHefPublishJobType(graphene.ObjectType):
    task_id = graphene.String()
    status = graphene.String()
    progress = graphene.String()
    commit_sha = graphene.String()
    github_url = graphene.String()
    file_paths = graphene.List(graphene.String)
    requested_platforms = graphene.List(graphene.String)
    deployed_platforms = graphene.List(graphene.String)
    deployment_results = graphene.JSONString()
    failure_summary = graphene.JSONString()
    rule_id = graphene.UUID()
    error_message = graphene.String()
    created_at = graphene.DateTime()
    started_at = graphene.DateTime()
    completed_at = graphene.DateTime()


class HefBundleDescriptorType(graphene.ObjectType):
    """A single discoverable OpenTIDE HEF bundle in a Git repository."""
    path = graphene.String()
    mdr_title = graphene.String()
    mdr_uuid = graphene.String()
    status = graphene.String()
    techniques = graphene.List(graphene.String)
    last_commit = graphene.String()
    valid = graphene.Boolean()
    validation_errors = graphene.List(graphene.String)


class HefBundleImportResultType(graphene.ObjectType):
    bundle_path = graphene.String()
    workbench_id = graphene.UUID()
    status = graphene.String()
    errors = graphene.List(graphene.String)


class OpenTideHefImportJobType(graphene.ObjectType):
    task_id = graphene.String()
    status = graphene.String()
    progress = graphene.String()
    repo_owner = graphene.String()
    repo_name = graphene.String()
    branch = graphene.String()
    target_folder = graphene.String()
    source_commit_sha = graphene.String()
    conflict_mode = graphene.String()
    import_platform_rules = graphene.Boolean()
    dry_run = graphene.Boolean()
    results = graphene.List(HefBundleImportResultType)
    error_message = graphene.String()
    created_at = graphene.DateTime()
    started_at = graphene.DateTime()
    completed_at = graphene.DateTime()

    def resolve_results(self, info):
        raw = self.results or []
        return [
            HefBundleImportResultType(
                bundle_path=r.get('bundle_path'),
                workbench_id=r.get('workbench_id'),
                status=r.get('status'),
                errors=r.get('errors') or [],
            )
            for r in raw
        ]


class DeploymentPlatformOptionType(graphene.ObjectType):
    key = graphene.String()
    label = graphene.String()


class DacDeploymentConfigType(graphene.ObjectType):
    mode = graphene.String()
    target_repository_id = graphene.UUID()
    target_repository_name = graphene.String()
    target_branch = graphene.String()
    target_folder = graphene.String()
    target_platforms = graphene.List(graphene.String)
    publish_profile_id = graphene.UUID()
    updated_by_id = graphene.UUID()
    updated_at = graphene.DateTime()
    created_at = graphene.DateTime()

    def resolve_target_repository_id(self, info):
        return self.target_repository_id

    def resolve_target_repository_name(self, info):
        return self.target_repository.name if self.target_repository else None

    def resolve_target_platforms(self, info):
        return self.target_platforms or []

    def resolve_publish_profile_id(self, info):
        return self.publish_profile_id

    def resolve_updated_by_id(self, info):
        return self.updated_by_id


class SmtpSettingsType(graphene.ObjectType):
    smtp_server = graphene.String()
    smtp_port = graphene.Int()
    encryption = graphene.String()
    login_method = graphene.String()
    smtp_username = graphene.String()
    has_password = graphene.Boolean()
    from_email = graphene.String()
    updated_at = graphene.DateTime()
    source = graphene.String()
    shared_profile_id = graphene.UUID()
    shared_profile_name = graphene.String()
    enforce_shared = graphene.Boolean()
    custom_configured = graphene.Boolean()
    can_edit_custom = graphene.Boolean()
    organization_id = graphene.UUID()

    def resolve_has_password(self, info):
        return bool(getattr(self, 'has_password', False))

    def resolve_source(self, info):
        return getattr(self, 'source', 'UNKNOWN')

    def resolve_shared_profile_id(self, info):
        return getattr(self, 'shared_profile_id', None)

    def resolve_shared_profile_name(self, info):
        return getattr(self, 'shared_profile_name', '')

    def resolve_enforce_shared(self, info):
        return bool(getattr(self, 'enforce_shared', False))

    def resolve_custom_configured(self, info):
        return bool(getattr(self, 'custom_configured', False))

    def resolve_can_edit_custom(self, info):
        # Org admins cannot edit custom SMTP when shared profile is locked.
        return not bool(getattr(self, 'enforce_shared', False))

    def resolve_organization_id(self, info):
        return getattr(self, 'organization_id', None)


class SharedSmtpProfileType(graphene.ObjectType):
    id = graphene.UUID()
    name = graphene.String()
    smtp_server = graphene.String()
    smtp_port = graphene.Int()
    encryption = graphene.String()
    login_method = graphene.String()
    smtp_username = graphene.String()
    has_password = graphene.Boolean()
    from_email = graphene.String()
    is_active = graphene.Boolean()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()

    def resolve_has_password(self, info):
        return bool(getattr(self, 'has_password', False))


# ---------------------------------------------------------------------------
# HEFAISTOS instance sharing (PULL-only)
# ---------------------------------------------------------------------------

class HefaistosInstanceIdentityType(graphene.ObjectType):
    instance_id = graphene.UUID()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()


class HefaistosRemotePeerType(graphene.ObjectType):
    id = graphene.UUID()
    name = graphene.String()
    remote_url = graphene.String()
    remote_instance_id = graphene.UUID()
    default_scope = graphene.String()
    auto_pull_enabled = graphene.Boolean()
    auto_pull_schedule = graphene.String()
    next_auto_pull_at = graphene.DateTime()
    verify_ssl = graphene.Boolean()
    allow_self_signed = graphene.Boolean()
    tls_cert_fingerprint = graphene.String()
    enabled = graphene.Boolean()
    has_api_key = graphene.Boolean()
    last_sync_at = graphene.DateTime()
    last_sync_status = graphene.String()
    last_sync_message = graphene.String()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()

    def resolve_has_api_key(self, info):
        return bool(getattr(self, 'has_api_key', False))


class HefaistosInboundShareKeyType(graphene.ObjectType):
    id = graphene.UUID()
    name = graphene.String()
    key_hint = graphene.String()
    allowed_scopes = graphene.List(graphene.String)
    enforce_tag_filter = graphene.Boolean()
    required_tags = graphene.List(graphene.String)
    is_active = graphene.Boolean()
    expires_at = graphene.DateTime()
    last_used_at = graphene.DateTime()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()

    def resolve_allowed_scopes(self, info):
        return [str(scope).upper() for scope in (self.allowed_scopes or []) if str(scope).strip()]

    def resolve_required_tags(self, info):
        return effective_required_tags(self)


class HefaistosPullJobType(graphene.ObjectType):
    id = graphene.UUID()
    peer_id = graphene.UUID()
    peer_name = graphene.String()
    requested_scope = graphene.String()
    status = graphene.String()
    summary = graphene.JSONString()
    message = graphene.String()
    started_at = graphene.DateTime()
    completed_at = graphene.DateTime()
    triggered_by_username = graphene.String()

    def resolve_peer_id(self, info):
        return self.peer_id

    def resolve_peer_name(self, info):
        return self.peer.name if getattr(self, 'peer', None) else None

    def resolve_triggered_by_username(self, info):
        return self.triggered_by.username if getattr(self, 'triggered_by', None) else None


# ---------------------------------------------------------------------------
# Organization AI Tasks
# ---------------------------------------------------------------------------

class OrgAITaskConfigType(graphene.ObjectType):
    task_key = graphene.String()
    title = graphene.String()
    description = graphene.String()
    ai_required = graphene.Boolean()
    enabled = graphene.Boolean()
    schedule = graphene.String()
    day_of_week = graphene.Int()
    day_of_month = graphene.Int()
    run_hour = graphene.Int()
    run_minute = graphene.Int()
    next_run_at = graphene.DateTime()
    last_run_at = graphene.DateTime()
    last_status = graphene.String()
    last_message = graphene.String()
    updated_at = graphene.DateTime()

    def resolve_title(self, info):
        task = get_ai_task_definition(self.task_key)
        return task.title if task else self.task_key

    def resolve_description(self, info):
        task = get_ai_task_definition(self.task_key)
        return task.description if task else ''

    def resolve_ai_required(self, info):
        task = get_ai_task_definition(self.task_key)
        return bool(task.ai_required) if task else False


class OrgAITaskRunType(graphene.ObjectType):
    id = graphene.UUID()
    task_key = graphene.String()
    title = graphene.String()
    status = graphene.String()
    trigger = graphene.String()
    started_at = graphene.DateTime()
    completed_at = graphene.DateTime()
    duration_ms = graphene.Int()
    output_summary = graphene.String()
    error_message = graphene.String()
    run_by_username = graphene.String()

    def resolve_title(self, info):
        task = get_ai_task_definition(self.task_key)
        return task.title if task else self.task_key

    def resolve_run_by_username(self, info):
        return self.run_by.username if getattr(self, 'run_by', None) else None


class PlatformGlobalKpisType(graphene.ObjectType):
    organizations = graphene.Int()
    users = graphene.Int()
    rules_total = graphene.Int()
    active_rules = graphene.Int()
    workbenches_total = graphene.Int()
    deployed_workbenches = graphene.Int()
    l1_entries = graphene.Int()
    orgs_with_shared_ai = graphene.Int()
    orgs_with_shared_smtp = graphene.Int()
    orgs_with_custom_ai = graphene.Int()
    orgs_with_custom_smtp = graphene.Int()
    orgs_near_user_capacity = graphene.Int()
    orgs_without_admin = graphene.Int()


class PlatformOrganizationStatType(graphene.ObjectType):
    organization_id = graphene.UUID()
    organization_name = graphene.String()
    max_users = graphene.Int()
    member_count = graphene.Int()
    user_utilization_percent = graphene.Float()
    admin_count = graphene.Int()
    rules_total = graphene.Int()
    active_rules = graphene.Int()
    workbenches_total = graphene.Int()
    deployed_workbenches = graphene.Int()
    l1_entries = graphene.Int()
    ai_shared_enabled = graphene.Boolean()
    smtp_shared_enabled = graphene.Boolean()
    last_activity_at = graphene.DateTime()
    users_growth_30d = graphene.Int()
    rules_growth_30d = graphene.Int()
    deployments_30d = graphene.Int()
    activity_score_30d = graphene.Int()


class PlatformAlertType(graphene.ObjectType):
    severity = graphene.String()
    category = graphene.String()
    organization_id = graphene.UUID()
    organization_name = graphene.String()
    message = graphene.String()


class PlatformTrendSummaryType(graphene.ObjectType):
    users_current = graphene.Int()
    users_30d_ago = graphene.Int()
    users_growth_30d = graphene.Int()
    rules_current = graphene.Int()
    rules_30d_ago = graphene.Int()
    rules_growth_30d = graphene.Int()
    deployments_30d = graphene.Int()


class PlatformTrendPointType(graphene.ObjectType):
    date = graphene.Date()
    users_total = graphene.Int()
    rules_total = graphene.Int()
    deployments = graphene.Int()


class PlatformTopOrganizationType(graphene.ObjectType):
    organization_id = graphene.UUID()
    organization_name = graphene.String()
    users_growth_30d = graphene.Int()
    rules_growth_30d = graphene.Int()
    deployments_30d = graphene.Int()
    activity_score_30d = graphene.Int()
    last_activity_at = graphene.DateTime()


class PlatformStatsType(graphene.ObjectType):
    generated_at = graphene.DateTime()
    inactivity_days = graphene.Int()
    global_kpis = graphene.Field(PlatformGlobalKpisType)
    organizations = graphene.List(PlatformOrganizationStatType)
    alerts = graphene.List(PlatformAlertType)
    trend_30d = graphene.Field(PlatformTrendSummaryType)
    daily_trends = graphene.List(PlatformTrendPointType)
    top_organizations = graphene.List(PlatformTopOrganizationType)


# ---------------------------------------------------------------------------
# OpenTIDE AI Preview types
# ---------------------------------------------------------------------------

class OpenTideFieldMetadata(graphene.ObjectType):
    """Metadata about a single OpenTide field (AI-generated marker)."""

    field_path = graphene.String(description="Dot-notation path to the field, e.g. 'mdr.response.procedure.analysis'")
    value = graphene.String(description="Field value serialised as JSON string")
    ai_generated = graphene.Boolean(description="True if this field was generated by AI")
    source = graphene.String(description="'user' | 'ai' | 'default'")
    field_type = graphene.String(description="'string' | 'array' | 'object' | 'number' | 'boolean'")


class PreviewOpenTideMetadata(graphene.ObjectType):
    """Preview of OpenTide metadata with AI enrichment markers."""

    tvm_yaml = graphene.JSONString(description="TVM (Threat Vector Model) structure as JSON, including threat.surface")
    mdr_yaml = graphene.JSONString(description="Complete MDR structure as JSON (detection rules are user-provided)")
    bdr_yaml = graphene.JSONString(description="BDR structure (null if not applicable)")
    dom_yaml = graphene.JSONString(description="DOM structure as JSON")
    field_metadata = graphene.List(
        OpenTideFieldMetadata,
        description="Per-field metadata indicating AI-generated fields",
    )
    ai_classification = graphene.String(description="'THREAT' or 'BUSINESS'")
    bdr_applicable = graphene.Boolean(description="True if BDR should be generated")
    validation_errors = graphene.List(graphene.String)
    total_fields = graphene.Int(description="Total number of tracked metadata fields")
    ai_generated_count = graphene.Int(description="Number of AI-generated fields")
    user_provided_count = graphene.Int(description="Number of user-provided fields")


class FieldOverrideInput(graphene.InputObjectType):
    """User-supplied override for a single OpenTIDE metadata field."""

    field_path = graphene.String(required=True, description="Dot-notation path, e.g. 'mdr.response.procedure.analysis'")
    value = graphene.String(required=True, description="New field value serialised as JSON")


# ---------------------------------------------------------------------------
# OpentidePreviewTask GraphQL types
# ---------------------------------------------------------------------------

class OpentidePreviewTaskType(graphene.ObjectType):
    """Status and result of an async OpenTIDE preview task."""

    id = graphene.UUID()
    status = graphene.String()
    use_ai_enrichment = graphene.Boolean()
    force_bdr_generation = graphene.Boolean()
    result = graphene.Field(PreviewOpenTideMetadata)
    error_message = graphene.String()
    created_at = graphene.DateTime()
    started_at = graphene.DateTime()
    completed_at = graphene.DateTime()


class Query(graphene.ObjectType):
    my_organization = graphene.Field(OrganizationType)
    organization = graphene.Field(OrganizationType, id=graphene.UUID(required=True))
    all_organizations = graphene.List(OrganizationType)
    all_entities = graphene.List(EntityType)
    misp_instances = graphene.List(MISPInstanceType, description="MISP instances for the current user's organization")
    preview_opentide_metadata = graphene.Field(
        PreviewOpenTideMetadata,
        playbook_id=graphene.UUID(required=True),
        use_ai_enrichment=graphene.Boolean(default_value=False),
        force_bdr_generation=graphene.Boolean(default_value=False),
        description=(
            "Preview OpenTIDE metadata for a playbook (synchronous). "
            "AI enrichment is optional/manual; detection rules are never AI-generated. "
            "For long-running AI enrichment prefer startOpentidePreviewTask / opentidePreviewStatus."
        ),
    )
    opentide_preview_status = graphene.Field(
        OpentidePreviewTaskType,
        task_id=graphene.UUID(required=True),
        description="Poll the status and result of an async OpenTIDE preview task.",
    )
    latest_opentide_preview = graphene.Field(
        OpentidePreviewTaskType,
        playbook_id=graphene.UUID(required=True),
        description=(
            "Return the most recent successfully completed OpenTIDE preview task "
            "for the given playbook. Returns null when no completed preview exists yet."
        ),
    )
    opentide_hef_publish_profiles = graphene.List(
        OpenTidePublishProfileType,
        enabled=graphene.Boolean(required=False),
        description='List OpenTIDE HEF publish profiles for the current organisation.',
    )
    opentide_hef_publish_job_status = graphene.Field(
        OpenTideHefPublishJobType,
        task_id=graphene.UUID(required=True),
        description='Check the status of an asynchronous OpenTIDE HEF publish job.',
    )
    list_hef_bundles = graphene.List(
        HefBundleDescriptorType,
        profile_id=graphene.UUID(required=False),
        repo_owner=graphene.String(required=False),
        repo_name=graphene.String(required=False),
        branch=graphene.String(required=False),
        commit_sha=graphene.String(required=False),
        target_folder=graphene.String(required=False),
        description='List discoverable OpenTIDE HEF bundles in a Git repository.',
    )
    my_opentide_hef_import_jobs = graphene.List(
        OpenTideHefImportJobType,
        limit=graphene.Int(required=False, default_value=20),
        description='List the current user\'s recent OpenTIDE HEF import jobs.',
    )
    dac_deployment_config = graphene.Field(
        DacDeploymentConfigType,
        description='Current organisation DaC deployment configuration (admin only).',
    )
    available_deployment_platforms = graphene.List(
        DeploymentPlatformOptionType,
        description='Deployment platforms supported by configured deploy connectors.',
    )
    smtp_settings = graphene.Field(
        SmtpSettingsType,
        organization_id=graphene.UUID(required=False),
        description='Effective SMTP settings for an organization (admin only).',
    )
    shared_smtp_profiles = graphene.List(
        SharedSmtpProfileType,
        include_inactive=graphene.Boolean(required=False, default_value=False),
        description='System-wide shared SMTP profiles (superuser only).',
    )
    platform_credentials = graphene.List(
        PlatformCredentialType,
        description="List platform credentials configured for the current user's organisation.",
    )
    hefaistos_instance_identity = graphene.Field(
        HefaistosInstanceIdentityType,
        description='Organization-scoped HEFAISTOS sharing identifier (UUID v5).',
    )
    hefaistos_remote_peers = graphene.List(
        HefaistosRemotePeerType,
        description='Configured remote HEFAISTOS peers for PULL synchronization (admin only).',
    )
    hefaistos_inbound_share_keys = graphene.List(
        HefaistosInboundShareKeyType,
        description='Inbound API keys allowing remote instances to PULL read-only data (admin only).',
    )
    hefaistos_pull_jobs = graphene.List(
        HefaistosPullJobType,
        limit=graphene.Int(required=False, default_value=20),
        description='Recent HEFAISTOS PULL synchronization jobs (admin only).',
    )
    org_ai_task_configs = graphene.List(
        OrgAITaskConfigType,
        description='Organization AI task configuration catalog (admin only).',
    )
    org_ai_task_runs = graphene.List(
        OrgAITaskRunType,
        limit=graphene.Int(required=False, default_value=30),
        task_key=graphene.String(required=False),
        description='Recent organization AI task runs (admin only).',
    )
    platform_stats = graphene.Field(
        PlatformStatsType,
        inactivity_days=graphene.Int(required=False, default_value=30),
        description='System-wide platform statistics for superusers.',
    )
    my_billing_profile = graphene.Field(
        OrganizationBillingProfileType,
        description='Current organization billing quotas and Stripe linkage.',
    )
    my_managed_organizations = graphene.List(
        OrganizationType,
        description='Organizations manageable by the current admin/resource manager.',
    )
    my_organization_manager_access = graphene.List(
        OrganizationManagerAccessType,
        description='Detailed manager-access bindings for the current user.',
    )

    def resolve_my_organization(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        return user.organization

    def resolve_organization(self, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        try:
            return Organization.objects.get(pk=id)
        except Organization.DoesNotExist:
            raise Exception("Organization not found")
    
    def resolve_all_organizations(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        # Only superusers can list all organizations
        if not user.is_superuser:
            raise Exception("Permission denied. Superuser access required.")
        return Organization.objects.select_related(
            'entity',
            'smtp_settings',
            'ai_settings',
        ).all().order_by('name')
    
    def resolve_all_entities(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        if not user.is_superuser:
            raise Exception("Permission denied. Superuser access required.")
        return Entity.objects.all().order_by('name')

    def resolve_misp_instances(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")
        return MISPInstance.objects.filter(organization=user.organization)

    def resolve_platform_credentials(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")
        return PlatformCredential.objects.filter(organization=user.organization)

    def resolve_hefaistos_instance_identity(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        return get_or_create_instance_identity(organization=user.organization)

    def resolve_hefaistos_remote_peers(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        if user.role not in (Roles.ADMIN,) and not user.is_superuser and not user.is_staff:
            raise GraphQLError('Permission denied')
        return HefaistosRemotePeer.objects.filter(organization=user.organization).order_by('name')

    def resolve_hefaistos_inbound_share_keys(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        if user.role not in (Roles.ADMIN,) and not user.is_superuser and not user.is_staff:
            raise GraphQLError('Permission denied')
        return HefaistosInboundShareKey.objects.filter(organization=user.organization).order_by('name')

    def resolve_hefaistos_pull_jobs(self, info, limit=20):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        if user.role not in (Roles.ADMIN,) and not user.is_superuser and not user.is_staff:
            raise GraphQLError('Permission denied')
        max_limit = max(1, min(int(limit or 20), 100))
        return HefaistosPullJob.objects.filter(
            organization=user.organization,
        ).select_related(
            'peer', 'triggered_by',
        ).order_by('-started_at')[:max_limit]

    def resolve_org_ai_task_configs(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        if user.role not in (Roles.ADMIN,) and not user.is_superuser and not user.is_staff:
            raise GraphQLError('Permission denied')
        return ensure_org_task_configs(user.organization, updated_by=user)

    def resolve_org_ai_task_runs(self, info, limit=30, task_key=None):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        if user.role not in (Roles.ADMIN,) and not user.is_superuser and not user.is_staff:
            raise GraphQLError('Permission denied')
        max_limit = max(1, min(int(limit or 30), 100))
        qs = OrganizationAITaskRun.objects.filter(organization=user.organization).select_related('run_by')
        if task_key:
            qs = qs.filter(task_key=task_key)
        return list(qs.order_by('-started_at')[:max_limit])

    def resolve_platform_stats(self, info, inactivity_days=30):
        from playbooks.models import L1PortalEntry, PlaybookGraph
        from rules.models import DetectionRule

        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        if not user.is_superuser:
            raise GraphQLError('Permission denied. Superuser access required.')

        now = timezone.now()
        inactivity_days = max(7, min(int(inactivity_days or 30), 365))
        inactivity_cutoff = now - timedelta(days=inactivity_days)

        trend_window_days = 30
        trend_cutoff = now - timedelta(days=trend_window_days)
        trend_window_start_date = (now - timedelta(days=trend_window_days - 1)).date()

        orgs_qs = Organization.objects.annotate(
            member_count=Count('customuser', distinct=True),
            admin_count=Count('customuser', filter=Q(customuser__role=Roles.ADMIN), distinct=True),
            rules_total=Count('detection_rules', distinct=True),
            active_rules=Count('detection_rules', filter=Q(detection_rules__playbook__status='DEPLOYED'), distinct=True),
            workbenches_total=Count('playbookgraph', distinct=True),
            deployed_workbenches=Count('playbookgraph', filter=Q(playbookgraph__status='DEPLOYED'), distinct=True),
            l1_entries=Count('l1_portal_entries', distinct=True),
            new_users_30d=Count('customuser', filter=Q(customuser__date_joined__gte=trend_cutoff), distinct=True),
            new_rules_30d=Count('detection_rules', filter=Q(detection_rules__created_at__gte=trend_cutoff), distinct=True),
            deployments_30d=Count(
                'playbookgraph',
                filter=Q(playbookgraph__status='DEPLOYED', playbookgraph__updated_at__gte=trend_cutoff),
                distinct=True,
            ),
            last_user_login=Max('customuser__last_login'),
            last_rule_update=Max('detection_rules__updated_at'),
            last_workbench_update=Max('playbookgraph__updated_at'),
        ).order_by('name')

        orgs = list(orgs_qs)
        org_ids = [org.id for org in orgs]
        org_ids_set = {str(org_id) for org_id in org_ids}

        smtp_shared_org_ids = {
            str(org_id)
            for org_id in OrganizationSmtpSettings.objects.filter(
                organization_id__in=org_ids,
                enforce_shared=True,
            ).values_list('organization_id', flat=True)
        }
        smtp_custom_org_ids = {
            str(org_id)
            for org_id in OrganizationSmtpSettings.objects.filter(
                organization_id__in=org_ids,
                custom_enabled=True,
                enforce_shared=False,
            ).values_list('organization_id', flat=True)
        }

        org_ai_settings = list(
            OrgAISettings.objects.select_related('shared_profile').filter(
                organization_id__in=org_ids,
            )
        )
        ai_shared_org_ids = {
            str(settings.organization_id)
            for settings in org_ai_settings
            if settings.shared_profile_locked
        }
        ai_custom_org_ids = {
            str(settings.organization_id)
            for settings in org_ai_settings
            if settings.has_any_provider and not settings.shared_profile_locked
        }

        near_capacity_count = 0
        without_admin_count = 0
        alerts: List[PlatformAlertType] = []
        org_rows: List[PlatformOrganizationStatType] = []
        top_candidates: List[PlatformTopOrganizationType] = []

        for org in orgs:
            org_id_str = str(org.id)
            member_count = int(getattr(org, 'member_count', 0) or 0)
            max_users = getattr(org, 'max_users', None)
            admin_count = int(getattr(org, 'admin_count', 0) or 0)
            rules_total = int(getattr(org, 'rules_total', 0) or 0)
            active_rules = int(getattr(org, 'active_rules', 0) or 0)
            workbenches_total = int(getattr(org, 'workbenches_total', 0) or 0)
            deployed_workbenches = int(getattr(org, 'deployed_workbenches', 0) or 0)
            l1_entries = int(getattr(org, 'l1_entries', 0) or 0)
            users_growth_30d = int(getattr(org, 'new_users_30d', 0) or 0)
            rules_growth_30d = int(getattr(org, 'new_rules_30d', 0) or 0)
            deployments_30d = int(getattr(org, 'deployments_30d', 0) or 0)
            activity_score_30d = users_growth_30d + rules_growth_30d + deployments_30d

            utilization_percent = None
            if max_users:
                utilization_percent = round((member_count / max_users) * 100, 2)
                if utilization_percent >= 90:
                    near_capacity_count += 1
                    alerts.append(
                        PlatformAlertType(
                            severity='critical' if utilization_percent >= 100 else 'warning',
                            category='USER_CAPACITY',
                            organization_id=org.id,
                            organization_name=org.name,
                            message=(
                                f'Organization is at {utilization_percent:.1f}% user capacity '
                                f'({member_count}/{max_users}).'
                            ),
                        )
                    )

            if admin_count == 0:
                without_admin_count += 1
                alerts.append(
                    PlatformAlertType(
                        severity='critical',
                        category='ORG_ADMIN',
                        organization_id=org.id,
                        organization_name=org.name,
                        message='Organization has no ADMIN user assigned.',
                    )
                )

            if active_rules == 0 and deployed_workbenches == 0:
                alerts.append(
                    PlatformAlertType(
                        severity='warning',
                        category='DEPLOYMENT',
                        organization_id=org.id,
                        organization_name=org.name,
                        message='No deployed workbenches and no active rules.',
                    )
                )

            activity_candidates = [
                getattr(org, 'updated_at', None),
                getattr(org, 'last_user_login', None),
                getattr(org, 'last_rule_update', None),
                getattr(org, 'last_workbench_update', None),
            ]
            present_activity = [value for value in activity_candidates if value is not None]
            last_activity_at = max(present_activity) if present_activity else None

            if last_activity_at is None or last_activity_at < inactivity_cutoff:
                alerts.append(
                    PlatformAlertType(
                        severity='warning',
                        category='INACTIVITY',
                        organization_id=org.id,
                        organization_name=org.name,
                        message=f'No recent activity in the last {inactivity_days} days.',
                    )
                )

            org_rows.append(
                PlatformOrganizationStatType(
                    organization_id=org.id,
                    organization_name=org.name,
                    max_users=max_users,
                    member_count=member_count,
                    user_utilization_percent=utilization_percent,
                    admin_count=admin_count,
                    rules_total=rules_total,
                    active_rules=active_rules,
                    workbenches_total=workbenches_total,
                    deployed_workbenches=deployed_workbenches,
                    l1_entries=l1_entries,
                    ai_shared_enabled=org_id_str in ai_shared_org_ids,
                    smtp_shared_enabled=org_id_str in smtp_shared_org_ids,
                    last_activity_at=last_activity_at,
                    users_growth_30d=users_growth_30d,
                    rules_growth_30d=rules_growth_30d,
                    deployments_30d=deployments_30d,
                    activity_score_30d=activity_score_30d,
                )
            )
            top_candidates.append(
                PlatformTopOrganizationType(
                    organization_id=org.id,
                    organization_name=org.name,
                    users_growth_30d=users_growth_30d,
                    rules_growth_30d=rules_growth_30d,
                    deployments_30d=deployments_30d,
                    activity_score_30d=activity_score_30d,
                    last_activity_at=last_activity_at,
                )
            )

        top_organizations = sorted(
            top_candidates,
            key=lambda item: (
                -(item.activity_score_30d or 0),
                -(item.users_growth_30d or 0),
                -(item.rules_growth_30d or 0),
                -(item.deployments_30d or 0),
                (item.organization_name or '').lower(),
            ),
        )[:5]

        users_current = CustomUser.objects.filter(organization_id__in=org_ids).count()
        users_30d_ago = CustomUser.objects.filter(
            organization_id__in=org_ids,
            date_joined__lt=trend_cutoff,
        ).count()
        users_growth_30d = users_current - users_30d_ago

        rules_current = DetectionRule.objects.filter(organization_id__in=org_ids).count()
        rules_30d_ago = DetectionRule.objects.filter(
            organization_id__in=org_ids,
            created_at__lt=trend_cutoff,
        ).count()
        rules_growth_30d = rules_current - rules_30d_ago

        deployments_30d_total = PlaybookGraph.objects.filter(
            organization_id__in=org_ids,
            status='DEPLOYED',
            updated_at__gte=trend_cutoff,
        ).count()

        trend_30d = PlatformTrendSummaryType(
            users_current=users_current,
            users_30d_ago=users_30d_ago,
            users_growth_30d=users_growth_30d,
            rules_current=rules_current,
            rules_30d_ago=rules_30d_ago,
            rules_growth_30d=rules_growth_30d,
            deployments_30d=deployments_30d_total,
        )

        user_daily_created: Dict[str, int] = {
            row['day'].isoformat(): int(row['total'] or 0)
            for row in CustomUser.objects.filter(
                organization_id__in=org_ids,
                date_joined__date__gte=trend_window_start_date,
            ).annotate(day=TruncDate('date_joined')).values('day').annotate(total=Count('id'))
            if row['day']
        }
        rule_daily_created: Dict[str, int] = {
            row['day'].isoformat(): int(row['total'] or 0)
            for row in DetectionRule.objects.filter(
                organization_id__in=org_ids,
                created_at__date__gte=trend_window_start_date,
            ).annotate(day=TruncDate('created_at')).values('day').annotate(total=Count('id'))
            if row['day']
        }
        deployment_daily_counts: Dict[str, int] = {
            row['day'].isoformat(): int(row['total'] or 0)
            for row in PlaybookGraph.objects.filter(
                organization_id__in=org_ids,
                status='DEPLOYED',
                updated_at__date__gte=trend_window_start_date,
            ).annotate(day=TruncDate('updated_at')).values('day').annotate(total=Count('id'))
            if row['day']
        }

        users_running_total = CustomUser.objects.filter(
            organization_id__in=org_ids,
            date_joined__date__lt=trend_window_start_date,
        ).count()
        rules_running_total = DetectionRule.objects.filter(
            organization_id__in=org_ids,
            created_at__date__lt=trend_window_start_date,
        ).count()

        daily_trends: List[PlatformTrendPointType] = []
        for day_offset in range(trend_window_days):
            day_value = trend_window_start_date + timedelta(days=day_offset)
            day_key = day_value.isoformat()
            users_running_total += user_daily_created.get(day_key, 0)
            rules_running_total += rule_daily_created.get(day_key, 0)
            daily_trends.append(
                PlatformTrendPointType(
                    date=day_value,
                    users_total=users_running_total,
                    rules_total=rules_running_total,
                    deployments=deployment_daily_counts.get(day_key, 0),
                )
            )

        global_kpis = PlatformGlobalKpisType(
            organizations=len(orgs),
            users=users_current,
            rules_total=rules_current,
            active_rules=DetectionRule.objects.filter(
                organization_id__in=org_ids,
                playbook__status='DEPLOYED',
            ).count(),
            workbenches_total=PlaybookGraph.objects.filter(organization_id__in=org_ids).count(),
            deployed_workbenches=PlaybookGraph.objects.filter(
                organization_id__in=org_ids,
                status='DEPLOYED',
            ).count(),
            l1_entries=L1PortalEntry.objects.filter(
                organization_id__in=org_ids,
                graph__status='DEPLOYED',
            ).count(),
            orgs_with_shared_ai=len(ai_shared_org_ids & org_ids_set),
            orgs_with_shared_smtp=len(smtp_shared_org_ids & org_ids_set),
            orgs_with_custom_ai=len(ai_custom_org_ids & org_ids_set),
            orgs_with_custom_smtp=len(smtp_custom_org_ids & org_ids_set),
            orgs_near_user_capacity=near_capacity_count,
            orgs_without_admin=without_admin_count,
        )

        return PlatformStatsType(
            generated_at=now,
            inactivity_days=inactivity_days,
            global_kpis=global_kpis,
            organizations=org_rows,
            alerts=alerts,
            trend_30d=trend_30d,
            daily_trends=daily_trends,
            top_organizations=top_organizations,
        )

    def resolve_my_billing_profile(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')

        org = user.organization
        if not org:
            raise GraphQLError('No active organization context found.')

        profile = OrganizationBillingProfile.objects.filter(organization=org).first()
        if not profile:
            return None
        return OrganizationBillingProfileType(
            organization_id=org.id,
            stripe_customer_id=profile.stripe_customer_id,
            stripe_subscription_id=profile.stripe_subscription_id,
            included_users=profile.included_users,
            included_organizations=profile.included_organizations,
            extra_users=profile.extra_users,
            extra_organizations=profile.extra_organizations,
            max_users=profile.max_users,
            max_organizations=profile.max_organizations,
            is_stripe_configured=stripe_is_configured(),
            updated_at=profile.updated_at,
        )

    def resolve_my_managed_organizations(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')

        org_ids: Set[str] = set()
        if user.organization_id:
            org_ids.add(str(user.organization_id))

        extra_ids = OrganizationManagerAccess.objects.filter(user=user).values_list('organization_id', flat=True)
        org_ids.update(str(org_id) for org_id in extra_ids)
        return list(Organization.objects.filter(id__in=org_ids).order_by('name'))

    def resolve_my_organization_manager_access(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        return list(
            OrganizationManagerAccess.objects.select_related('organization', 'user')
            .filter(user=user)
            .order_by('organization__name')
        )

    def resolve_opentide_hef_publish_profiles(self, info, enabled=None):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        qs = OpenTidePublishProfile.objects.select_related('repository').filter(organization=user.organization)
        if enabled is not None:
            qs = qs.filter(enabled=enabled)
        return qs

    def resolve_dac_deployment_config(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        if user.role not in (Roles.ADMIN,) and not user.is_superuser and not user.is_staff:
            raise GraphQLError('Permission denied')
        config, _ = DacDeploymentConfig.objects.select_related(
            'target_repository',
            'publish_profile',
            'updated_by',
        ).get_or_create(
            organization=user.organization,
            defaults={'updated_by': user},
        )
        return config

    def resolve_available_deployment_platforms(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        if user.role not in (Roles.ADMIN,) and not user.is_superuser and not user.is_staff:
            raise GraphQLError('Permission denied')
        return [
            DeploymentPlatformOptionType(
                key=key,
                label=PLATFORM_DISPLAY_LABELS.get(key, key.replace('_', ' ').title()),
            )
            for key in sorted(PLATFORM_DEPLOYER_MAP.keys())
        ]

    def resolve_smtp_settings(self, info, organization_id=None):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        if user.role not in (Roles.ADMIN,) and not user.is_superuser and not user.is_staff:
            raise GraphQLError('Permission denied')
        target_org = user.organization
        if organization_id is not None:
            if not (user.is_superuser or user.is_staff):
                raise GraphQLError('Only superusers can read SMTP settings for other organizations.')
            try:
                target_org = Organization.objects.get(pk=organization_id)
            except Organization.DoesNotExist:
                raise GraphQLError('Organization not found')

        return get_effective_smtp_for_organization(target_org, create_if_missing=True)

    def resolve_shared_smtp_profiles(self, info, include_inactive=False):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError('Authentication required')
        if not (user.is_superuser or user.is_staff):
            raise GraphQLError('Permission denied. Superuser access required.')
        qs = SharedSmtpProfile.objects.all()
        if not include_inactive:
            qs = qs.filter(is_active=True)
        return list(qs.order_by('name'))

    def resolve_preview_opentide_metadata(
        self, info, playbook_id, use_ai_enrichment=False, force_bdr_generation=False
    ):
        import json as _json
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")

        from playbooks.models import PlaybookGraph
        from playbooks.utils.opentide_compiler import (
            compile_tvm_yaml,
            compile_mdr_yaml_with_ai,
            compile_dom_yaml_with_ai,
        )
        from playbooks.utils.opentide_validator import validate_mdr_structure

        try:
            playbook = PlaybookGraph.objects.select_related(
                'organization', 'author', 'mitre_technique'
            ).prefetch_related('tags', 'linked_rules').get(
                pk=playbook_id, organization=user.organization
            )
        except PlaybookGraph.DoesNotExist:
            raise GraphQLError("Playbook not found")

        # Resolve AI settings
        ai_settings = None
        if use_ai_enrichment:
            try:
                from ai_assistant.models import UserAISettings
                from ai_assistant.schema import _get_effective_ai_settings
                user_ai_settings, _ = UserAISettings.objects.get_or_create(user=user)
                if user_ai_settings.enable_auto_enrichment:
                    ai_settings = _get_effective_ai_settings(user_ai_settings)
            except Exception:
                pass

        # Compile with optional AI enrichment
        tvm_data = compile_tvm_yaml(playbook)
        mdr_data = compile_mdr_yaml_with_ai(playbook, ai_settings, use_ai_enrichment)
        dom_data = compile_dom_yaml_with_ai(playbook, ai_settings, use_ai_enrichment)

        # BDR framework is deprecated — never generate BDR objects.
        bdr_data = None
        bdr_applicable = False
        ai_classification = None

        # Extract field metadata (AI-generated markers)
        field_metadata = _extract_opentide_field_metadata(mdr_data, bdr_data, dom_data)

        # Validate
        is_valid, errors = validate_mdr_structure(mdr_data)

        # Strip internal tracking keys before returning to client
        mdr_out = _strip_ai_metadata(mdr_data)
        dom_out = _strip_ai_metadata(dom_data)

        return PreviewOpenTideMetadata(
            tvm_yaml=tvm_data,
            mdr_yaml=mdr_out,
            bdr_yaml=None,
            dom_yaml=dom_out,
            field_metadata=field_metadata,
            ai_classification=ai_classification,
            bdr_applicable=False,
            validation_errors=errors if not is_valid else [],
            total_fields=len(field_metadata),
            ai_generated_count=sum(1 for f in field_metadata if f.ai_generated),
            user_provided_count=sum(1 for f in field_metadata if not f.ai_generated),
        )

    def resolve_opentide_preview_status(self, info, task_id):
        """Return the current status (and result when COMPLETED) of an async preview task."""
        import json as _json
        from django.utils import timezone as _tz
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")

        from playbooks.models import OpentidePreviewTask
        try:
            task = OpentidePreviewTask.objects.select_related('playbook', 'user').get(
                pk=task_id, user=user
            )
        except OpentidePreviewTask.DoesNotExist:
            raise GraphQLError("Task not found")

        # Time-out tasks that have been stuck in RUNNING for more than 10 minutes
        # (e.g. AI model not responding).  This prevents the frontend from spinning
        # forever with no error shown.
        PREVIEW_TIMEOUT_SECONDS = 600  # 10 minutes
        if (
            task.status == OpentidePreviewTask.TaskStatus.RUNNING
            and task.started_at
            and (_tz.now() - task.started_at).total_seconds() > PREVIEW_TIMEOUT_SECONDS
        ):
            task.status = OpentidePreviewTask.TaskStatus.FAILED
            task.error_message = (
                'Preview task timed out after 10 minutes. '
                'The AI model may be unavailable or overloaded — please try again.'
            )
            task.completed_at = _tz.now()
            task.save(update_fields=['status', 'error_message', 'completed_at'])
            logger.warning("OpentidePreviewTask %s timed out and was marked FAILED.", task_id)

        result = None
        if task.status == OpentidePreviewTask.TaskStatus.COMPLETED and task.result_data:
            rd = task.result_data
            field_metadata_raw = rd.get('field_metadata', [])
            field_metadata = [
                OpenTideFieldMetadata(
                    field_path=f['field_path'],
                    value=f['value'],
                    ai_generated=f['ai_generated'],
                    source=f['source'],
                    field_type=f['field_type'],
                )
                for f in field_metadata_raw
            ]
            result = PreviewOpenTideMetadata(
                tvm_yaml=rd.get('tvm_yaml'),
                mdr_yaml=rd.get('mdr_yaml'),
                bdr_yaml=rd.get('bdr_yaml'),
                dom_yaml=rd.get('dom_yaml'),
                field_metadata=field_metadata,
                ai_classification=rd.get('ai_classification'),
                bdr_applicable=rd.get('bdr_applicable', False),
                validation_errors=rd.get('validation_errors', []),
                total_fields=rd.get('total_fields', 0),
                ai_generated_count=rd.get('ai_generated_count', 0),
                user_provided_count=rd.get('user_provided_count', 0),
            )

        return OpentidePreviewTaskType(
            id=task.id,
            status=task.status,
            use_ai_enrichment=task.use_ai_enrichment,
            force_bdr_generation=task.force_bdr_generation,
            result=result,
            error_message=task.error_message,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
        )

    def resolve_latest_opentide_preview(self, info, playbook_id):
        """Return the most recent completed preview task result for a playbook."""
        import json as _json
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")

        from playbooks.models import OpentidePreviewTask
        task = (
            OpentidePreviewTask.objects
            .filter(
                playbook__id=playbook_id,
                playbook__organization=user.organization,
                user=user,
                status=OpentidePreviewTask.TaskStatus.COMPLETED,
            )
            .order_by('-completed_at')
            .first()
        )
        if task is None:
            return None

        result = None
        if task.result_data:
            rd = task.result_data
            field_metadata_raw = rd.get('field_metadata', [])
            field_metadata = [
                OpenTideFieldMetadata(
                    field_path=f['field_path'],
                    value=f['value'],
                    ai_generated=f['ai_generated'],
                    source=f['source'],
                    field_type=f['field_type'],
                )
                for f in field_metadata_raw
            ]
            result = PreviewOpenTideMetadata(
                tvm_yaml=rd.get('tvm_yaml'),
                mdr_yaml=rd.get('mdr_yaml'),
                bdr_yaml=rd.get('bdr_yaml'),
                dom_yaml=rd.get('dom_yaml'),
                field_metadata=field_metadata,
                ai_classification=rd.get('ai_classification'),
                bdr_applicable=rd.get('bdr_applicable', False),
                validation_errors=rd.get('validation_errors', []),
                total_fields=rd.get('total_fields', 0),
                ai_generated_count=rd.get('ai_generated_count', 0),
                user_provided_count=rd.get('user_provided_count', 0),
            )

        return OpentidePreviewTaskType(
            id=task.id,
            status=task.status,
            use_ai_enrichment=task.use_ai_enrichment,
            force_bdr_generation=task.force_bdr_generation,
            result=result,
            error_message=task.error_message,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
        )

    def resolve_opentide_hef_publish_job_status(self, info, task_id):
        from django.utils import timezone as _tz

        user = info.context.user
        if user.is_anonymous:
            logger.warning(
                'HEF status poll rejected: anonymous user, task_id=%s',
                task_id,
            )
            raise GraphQLError('Authentication required')

        logger.info(
            'HEF status poll requested: task_id=%s user_id=%s org_id=%s',
            task_id,
            getattr(user, 'id', None),
            getattr(getattr(user, 'organization', None), 'id', None),
        )
        try:
            job = OpenTideHefPublishJob.objects.get(pk=task_id, organization=user.organization)
        except OpenTideHefPublishJob.DoesNotExist:
            logger.warning(
                'HEF status poll failed: task_id=%s not found for user_id=%s org_id=%s',
                task_id,
                getattr(user, 'id', None),
                getattr(getattr(user, 'organization', None), 'id', None),
            )
            raise GraphQLError('HEF publish job not found')

        JOB_TIMEOUT_SECONDS = 1200
        if (
            job.status == 'PROCESSING'
            and job.started_at
            and (_tz.now() - job.started_at).total_seconds() > JOB_TIMEOUT_SECONDS
        ):
            job.status = 'FAILED'
            job.error_message = 'HEF publish job timed out after 20 minutes.'
            job.failure_summary = {
                'failed_count': 1,
                'failed_platforms': [],
                'failure_type_counts': {'WORKER_TIMEOUT': 1},
                'operator_hints': ['Inspect worker logs and infrastructure queue/worker health.'],
            }
            job.completed_at = _tz.now()
            job.save(update_fields=['status', 'error_message', 'failure_summary', 'completed_at'])
            logger.warning(
                'HEF status poll timeout: task_id=%s marked FAILED',
                task_id,
            )

        logger.info(
            'HEF status poll response: task_id=%s status=%s commit_sha=%s error=%s',
            task_id,
            job.status,
            bool(job.commit_sha),
            bool(job.error_message),
        )

        return OpenTideHefPublishJobType(
            task_id=str(job.id),
            status=job.status,
            progress=job.progress,
            commit_sha=job.commit_sha or None,
            github_url=job.github_url or None,
            file_paths=job.file_paths or [],
            requested_platforms=job.requested_platforms or [],
            deployed_platforms=job.deployed_platforms or [],
            deployment_results=job.deployment_results or [],
            failure_summary=job.failure_summary or {},
            rule_id=job.rule_id,
            error_message=job.error_message or None,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )

    @role_required([Roles.ANALYST, Roles.ADMIN])
    def resolve_list_hef_bundles(
        self,
        info,
        profile_id=None,
        repo_owner=None,
        repo_name=None,
        branch=None,
        commit_sha=None,
        target_folder=None,
    ):
        from playbooks.hef_import import discover_hef_bundles, fetch_bundle_files, validate_bundle
        import yaml as _yaml

        user = info.context.user

        # Resolve credentials
        _token = None
        _repo_owner = repo_owner
        _repo_name = repo_name
        _branch = branch or 'main'
        _target_folder = target_folder or ''
        _provider = 'GITHUB'
        _api_base_url = None
        _verify_ssl = True
        _repo_url = f'https://github.com/{_repo_owner}/{_repo_name}' if _repo_owner and _repo_name else None

        if profile_id:
            try:
                profile = OpenTidePublishProfile.objects.select_related('repository').get(
                    pk=profile_id, organization=user.organization
                )
            except OpenTidePublishProfile.DoesNotExist:
                raise GraphQLError('HEF publish profile not found')
            repo = profile.repository
            if not repo:
                raise GraphQLError('HEF publish profile has no repository configured')
            from playbooks.hef_publish import extract_repository_details
            details = extract_repository_details(repo.git_url)
            if not details:
                raise GraphQLError(f'Cannot parse owner/repo from URL: {repo.git_url}')
            _repo_owner, _repo_name, _provider = details
            _token = repo.token or ''
            _provider = repo.provider
            _api_base_url = repo.api_base_url
            _verify_ssl = bool(getattr(repo, 'verify_ssl', True))
            _repo_url = repo.git_url
            _branch = branch or profile.branch or 'main'
            _target_folder = target_folder or profile.target_folder or ''
        else:
            if not _repo_owner or not _repo_name:
                raise GraphQLError('Either profile_id or repo_owner + repo_name are required')
            _validate_github_component(_repo_owner, 'repo_owner')
            _validate_github_component(_repo_name, 'repo_name')
            # Look up token from matching repository
            from rules.models import RuleRepository
            repo_qs = RuleRepository.objects.filter(
                organization=user.organization,
                git_url__icontains=f'/{_repo_owner}/{_repo_name}',
            )
            repo_obj = repo_qs.first() if repo_qs.exists() else None
            _token = repo_obj.token if repo_obj else ''
            _provider = repo_obj.provider if repo_obj else 'GITHUB'
            _api_base_url = repo_obj.api_base_url if repo_obj else None
            _verify_ssl = bool(getattr(repo_obj, 'verify_ssl', True)) if repo_obj else True
            _repo_url = repo_obj.git_url if repo_obj else f'https://github.com/{_repo_owner}/{_repo_name}'

        if not _token:
            raise GraphQLError(
                f'No repository token configured for {_repo_owner}/{_repo_name}. '
                'Set up a RuleRepository or HEF publish profile with a PAT.'
            )

        _validate_branch(_branch)
        _validate_commit_sha(commit_sha or '')

        try:
            bundles, resolved_sha = discover_hef_bundles(
                _repo_owner, _repo_name, _branch, _token,
                target_folder=_target_folder,
                commit_sha=commit_sha or None,
                repo_url=_repo_url,
                provider=_provider,
                api_base_url=_api_base_url,
                verify_ssl=_verify_ssl,
            )
        except Exception as exc:
            raise GraphQLError(f'Bundle discovery failed: {exc}')

        result = []
        for bundle in bundles:
            # Enrich with MDR title / UUID / status / techniques if not yet populated
            # (fast-path from _hef_index.json already has these; tree-walk doesn't)
            mdr_title = bundle.get('mdr_title') or ''
            mdr_uuid = bundle.get('mdr_uuid') or ''
            status = bundle.get('status') or ''
            techniques = bundle.get('techniques') or []

            if not mdr_uuid and bundle.get('files', {}).get('mdr'):
                try:
                    file_paths = {
                        'mdr': bundle['files']['mdr'],
                        'tvm': bundle['files'].get('tvm'),
                        'dom': bundle['files'].get('dom'),
                        'bdr': bundle['files'].get('bdr'),
                    }
                    fetched = fetch_bundle_files(
                        _repo_owner,
                        _repo_name,
                        _token,
                        file_paths,
                        resolved_sha,
                        repo_url=_repo_url,
                        provider=_provider,
                        api_base_url=_api_base_url,
                        verify_ssl=_verify_ssl,
                    )
                    mdr_data = _yaml.safe_load(fetched.get('mdr') or '') or {}
                    mdr_meta = mdr_data.get('metadata') or {}
                    mdr_uuid = mdr_meta.get('uuid') or ''
                    mdr_title = mdr_meta.get('title') or mdr_data.get('name') or mdr_title
                    # Extract techniques from TVM
                    tvm_data = _yaml.safe_load(fetched.get('tvm') or '') or {}
                    techniques = list(tvm_data.get('threat', {}).get('att&ck') or [])
                    is_valid, validation_errors = validate_bundle(fetched)
                except Exception as exc:
                    logger.debug('HEF bundle enrichment failed for %s: %s', bundle['path'], exc)
                    is_valid, validation_errors = True, []
            else:
                is_valid = bundle.get('valid', True)
                validation_errors = bundle.get('validation_errors') or []

            result.append(HefBundleDescriptorType(
                path=bundle['path'],
                mdr_title=mdr_title,
                mdr_uuid=mdr_uuid,
                status=status,
                techniques=techniques,
                last_commit=bundle.get('last_commit') or resolved_sha,
                valid=is_valid,
                validation_errors=validation_errors,
            ))

        return result

    @role_required([Roles.ANALYST, Roles.ADMIN])
    def resolve_my_opentide_hef_import_jobs(self, info, limit=20):
        user = info.context.user
        return OpenTideHefImportJob.objects.filter(
            organization=user.organization,
        ).order_by('-created_at')[:limit]


_INTERNAL_YAML_KEYS = frozenset(['_ai_generated', '_validation_warning'])

# GitHub owner/repo name component: alphanumeric, hyphens, dots, underscores only
_GITHUB_COMPONENT_RE = re.compile(r'^[a-zA-Z0-9._-]{1,100}$')
# Git commit SHA: 7–40 lowercase hex characters
_COMMIT_SHA_RE = re.compile(r'^[0-9a-fA-F]{7,40}$')
# Git branch: printable non-space chars; forbid control chars and URL metacharacters
_BRANCH_RE = re.compile(r'^[^\x00-\x1f\x7f ?&#%]{1,250}$')


def _validate_github_component(value: str, label: str) -> None:
    """Raise GraphQLError if *value* is not a safe GitHub owner or repository name."""
    if not value or not _GITHUB_COMPONENT_RE.match(value):
        raise GraphQLError(
            f"Invalid {label} '{value}'. "
            'Must contain only alphanumeric characters, hyphens, dots, and underscores (max 100 chars).'
        )


def _validate_commit_sha(value: str) -> None:
    """Raise GraphQLError if *value* is not a valid git commit SHA (7-40 hex chars)."""
    if value and not _COMMIT_SHA_RE.match(value):
        raise GraphQLError(
            f"Invalid commit SHA '{value}'. Must be 7–40 hexadecimal characters."
        )


def _validate_branch(value: str) -> None:
    """Raise GraphQLError if *value* is not a safe git branch name."""
    if value and not _BRANCH_RE.match(value):
        raise GraphQLError(
            f"Invalid branch name '{value}'. Branch names must not contain spaces or URL special characters."
        )


def _strip_ai_metadata(data: dict) -> dict:
    """Return a copy of *data* with internal tracking keys removed."""
    return {k: v for k, v in data.items() if k not in _INTERNAL_YAML_KEYS}


def _get_nested_value(data: dict, path: str):
    """Get value from nested dict using dot-notation path."""
    keys = path.split('.')
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value


def _get_field_type(value) -> str:
    """Return a string type descriptor for *value*."""
    # NOTE: bool must be checked before int/float because bool is a subclass of int.
    # isinstance(True, int) returns True, so swapping these checks would classify
    # booleans as 'number'. Keep bool first.
    if isinstance(value, bool):
        return 'boolean'
    elif isinstance(value, (int, float)):
        return 'number'
    elif isinstance(value, str):
        return 'string'
    elif isinstance(value, list):
        return 'array'
    elif isinstance(value, dict):
        return 'object'
    return 'unknown'


def _apply_override(data: dict, path_parts: list, value) -> None:
    """Apply *value* to the nested dict *data* following *path_parts*."""
    target = data
    for part in path_parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            target[part] = {}
        target = target[part]
    if path_parts:
        target[path_parts[-1]] = value


def _extract_opentide_field_metadata(mdr_data: dict, bdr_data, dom_data: dict) -> list:
    """
    Build list of OpenTideFieldMetadata entries for AI-generated fields.

    Inspects the ``_ai_generated`` tracking dicts attached by the AI compiler
    variants and returns a flat list of field path + marker objects.
    """
    import json as _json
    metadata = []

    for prefix, data in (('mdr', mdr_data), ('dom', dom_data)):
        ai_gen = (data or {}).get('_ai_generated', {})
        for field_path, is_ai in ai_gen.items():
            value = _get_nested_value(data, field_path)
            metadata.append(OpenTideFieldMetadata(
                field_path=f"{prefix}.{field_path}",
                value=_json.dumps(value),
                ai_generated=bool(is_ai),
                source='ai' if is_ai else 'user',
                field_type=_get_field_type(value),
            ))

    if bdr_data:
        ai_gen_bdr = bdr_data.get('_ai_generated', {})
        for field_path, is_ai in ai_gen_bdr.items():
            value = _get_nested_value(bdr_data, field_path)
            metadata.append(OpenTideFieldMetadata(
                field_path=f"bdr.{field_path}",
                value=_json.dumps(value),
                ai_generated=bool(is_ai),
                source='ai' if is_ai else 'user',
                field_type=_get_field_type(value),
            ))

    return metadata


def _first_validation_error_message(exc: ValidationError) -> str:
    if hasattr(exc, "message_dict") and exc.message_dict:
        for field_errors in exc.message_dict.values():
            if field_errors:
                return str(field_errors[0])
    if hasattr(exc, "messages") and exc.messages:
        return str(exc.messages[0])
    return str(exc)


def _normalize_max_users_input(max_users):
    if max_users is _UNSET:
        return _UNSET
    if max_users is None:
        return None
    normalized = int(max_users)
    if normalized < 1:
        raise ValueError("Max users must be at least 1.")
    return normalized


def _caller_can_manage_organization(caller, organization_id) -> bool:
    if not caller or getattr(caller, 'is_anonymous', True):
        return False
    if getattr(caller, 'is_superuser', False) or getattr(caller, 'is_staff', False):
        return True
    if caller.organization_id and str(caller.organization_id) == str(organization_id):
        return caller.role in (Roles.ADMIN, Roles.RESOURCE_MANAGER)
    return OrganizationManagerAccess.objects.filter(
        user=caller,
        organization_id=organization_id,
    ).exists()


# --- Mutations ---

class CreateOrganization(graphene.Mutation):
    """Create a new organization (superuser only)."""
    
    class Arguments:
        name = graphene.String(required=True)
        entity_id = graphene.UUID(required=False)
        max_users = graphene.Int(required=False)
    
    organization = graphene.Field(OrganizationType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, name, entity_id=None, max_users=None):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        if not user.is_superuser:
            raise Exception("Permission denied. Superuser access required.")
        
        # Check if organization with this name already exists
        if Organization.objects.filter(name=name).exists():
            return CreateOrganization(
                organization=None,
                success=False,
                message=f"Organization with name '{name}' already exists."
            )
        
        entity = None
        if entity_id:
            try:
                entity = Entity.objects.get(pk=entity_id)
            except Entity.DoesNotExist:
                return CreateOrganization(
                    organization=None,
                    success=False,
                    message="Entity not found."
                )
        try:
            normalized_max_users = _normalize_max_users_input(max_users)
        except ValueError as exc:
            return CreateOrganization(
                organization=None,
                success=False,
                message=str(exc),
            )

        org = Organization(name=name, entity=entity, max_users=normalized_max_users)
        try:
            org.full_clean()
        except ValidationError as exc:
            return CreateOrganization(
                organization=None,
                success=False,
                message=_first_validation_error_message(exc),
            )
        org.save()
        return CreateOrganization(
            organization=org,
            success=True,
            message="Organization created successfully."
        )


class UpdateOrganization(graphene.Mutation):
    """Update an organization (superuser only)."""
    
    class Arguments:
        id = graphene.UUID(required=True)
        name = graphene.String(required=False)
        entity_id = graphene.UUID(required=False)
        max_users = graphene.Int(required=False)
    
    organization = graphene.Field(OrganizationType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, id, name=None, entity_id=_UNSET, max_users=_UNSET):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        if not user.is_superuser:
            raise Exception("Permission denied. Superuser access required.")
        
        try:
            org = Organization.objects.get(pk=id)
        except Organization.DoesNotExist:
            return UpdateOrganization(
                organization=None,
                success=False,
                message="Organization not found."
            )
        
        if name:
            # Check if another org has this name
            if Organization.objects.filter(name=name).exclude(pk=id).exists():
                return UpdateOrganization(
                    organization=None,
                    success=False,
                    message=f"Organization with name '{name}' already exists."
                )
            org.name = name

        if entity_id is not _UNSET:
            if entity_id is None:
                org.entity = None
            else:
                try:
                    entity = Entity.objects.get(pk=entity_id)
                    org.entity = entity
                except Entity.DoesNotExist:
                    return UpdateOrganization(
                        organization=None,
                        success=False,
                        message="Entity not found."
                    )

        if max_users is not _UNSET:
            try:
                org.max_users = _normalize_max_users_input(max_users)
            except ValueError as exc:
                return UpdateOrganization(
                    organization=None,
                    success=False,
                    message=str(exc),
                )

        try:
            org.full_clean()
        except ValidationError as exc:
            return UpdateOrganization(
                organization=None,
                success=False,
                message=_first_validation_error_message(exc),
            )

        org.save()
        return UpdateOrganization(
            organization=org,
            success=True,
            message="Organization updated successfully."
        )


class DeleteOrganization(graphene.Mutation):
    """Delete an organization (superuser only)."""
    
    class Arguments:
        id = graphene.UUID(required=True)
    
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        if not user.is_superuser:
            raise Exception("Permission denied. Superuser access required.")
        
        try:
            org = Organization.objects.get(pk=id)
        except Organization.DoesNotExist:
            return DeleteOrganization(
                success=False,
                message="Organization not found."
            )
        
        # Check if organization has members
        member_count = CustomUser.objects.filter(organization=org).count()
        if member_count > 0:
            return DeleteOrganization(
                success=False,
                message=f"Cannot delete organization with {member_count} member(s). Reassign or remove members first."
            )
        
        org.delete()
        return DeleteOrganization(
            success=True,
            message="Organization deleted successfully."
        )


class CreateEntity(graphene.Mutation):
    """Create a new entity/holding company (superuser only)."""
    
    class Arguments:
        name = graphene.String(required=True)
    
    entity = graphene.Field(EntityType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, name):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        if not user.is_superuser:
            raise Exception("Permission denied. Superuser access required.")
        
        if Entity.objects.filter(name=name).exists():
            return CreateEntity(
                entity=None,
                success=False,
                message=f"Entity with name '{name}' already exists."
            )
        
        entity = Entity.objects.create(name=name)
        return CreateEntity(
            entity=entity,
            success=True,
            message="Entity created successfully."
        )


class DeleteEntity(graphene.Mutation):
    """Delete an entity (superuser only)."""
    
    class Arguments:
        id = graphene.UUID(required=True)
    
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        if not user.is_superuser:
            raise Exception("Permission denied. Superuser access required.")
        
        try:
            entity = Entity.objects.get(pk=id)
        except Entity.DoesNotExist:
            return DeleteEntity(
                success=False,
                message="Entity not found."
            )
        
        # Check if entity has organizations
        org_count = entity.organizations.count()
        if org_count > 0:
            return DeleteEntity(
                success=False,
                message=f"Cannot delete entity with {org_count} organization(s). Reassign or remove organizations first."
            )
        
        entity.delete()
        return DeleteEntity(
            success=True,
            message="Entity deleted successfully."
        )


class CreateMISPInstance(graphene.Mutation):
    """Add a MISP instance to the current user's organization (Admin only, max 5)."""

    class Arguments:
        name = graphene.String(required=True)
        url = graphene.String(required=True)
        auth_key = graphene.String(required=True)
        verify_ssl = graphene.Boolean(required=False, default_value=True)
        auto_pull_enabled = graphene.Boolean(required=False, default_value=False)
        auto_pull_schedule = graphene.String(required=False, default_value='DAILY')
        auto_pull_tag = graphene.String(required=False, default_value='HEFAISTOS')

    misp_instance = graphene.Field(MISPInstanceType)
    success = graphene.Boolean()
    message = graphene.String()

    def mutate(
        self, info, name, url, auth_key, verify_ssl=True,
        auto_pull_enabled=False, auto_pull_schedule='DAILY', auto_pull_tag='HEFAISTOS',
    ):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")
        if user.role not in ("ADMIN",) and not user.is_superuser:
            raise GraphQLError("Permission denied. Admin role required.")
        org = user.organization
        if MISPInstance.objects.filter(organization=org).count() >= MISP_INSTANCE_LIMIT:
            return CreateMISPInstance(
                misp_instance=None,
                success=False,
                message=f"Maximum of {MISP_INSTANCE_LIMIT} MISP instances per organization reached.",
            )
        if MISPInstance.objects.filter(organization=org, name=name).exists():
            return CreateMISPInstance(
                misp_instance=None,
                success=False,
                message=f"A MISP instance named '{name}' already exists.",
            )
        instance = MISPInstance.objects.create(
            organization=org,
            name=name,
            url=url.rstrip("/"),
            auth_key=auth_key,
            verify_ssl=verify_ssl,
            auto_pull_enabled=auto_pull_enabled,
            auto_pull_schedule=(auto_pull_schedule or 'DAILY').strip().upper(),
            auto_pull_tag=(auto_pull_tag or '').strip(),
        )
        return CreateMISPInstance(misp_instance=instance, success=True, message="MISP instance created.")


class UpdateMISPInstance(graphene.Mutation):
    """Update a MISP instance (Admin only)."""

    class Arguments:
        id = graphene.UUID(required=True)
        name = graphene.String(required=False)
        url = graphene.String(required=False)
        auth_key = graphene.String(required=False)
        verify_ssl = graphene.Boolean(required=False)
        auto_pull_enabled = graphene.Boolean(required=False)
        auto_pull_schedule = graphene.String(required=False)
        auto_pull_tag = graphene.String(required=False)

    misp_instance = graphene.Field(MISPInstanceType)
    success = graphene.Boolean()
    message = graphene.String()

    def mutate(
        self, info, id, name=None, url=None, auth_key=None, verify_ssl=None,
        auto_pull_enabled=None, auto_pull_schedule=None, auto_pull_tag=None,
    ):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")
        if user.role not in ("ADMIN",) and not user.is_superuser:
            raise GraphQLError("Permission denied. Admin role required.")
        try:
            instance = MISPInstance.objects.get(pk=id, organization=user.organization)
        except MISPInstance.DoesNotExist:
            return UpdateMISPInstance(misp_instance=None, success=False, message="MISP instance not found.")
        if name is not None:
            if MISPInstance.objects.filter(organization=user.organization, name=name).exclude(pk=id).exists():
                return UpdateMISPInstance(misp_instance=None, success=False, message=f"A MISP instance named '{name}' already exists.")
            instance.name = name
        if url is not None:
            instance.url = url.rstrip("/")
        if auth_key is not None:
            instance.auth_key = auth_key
        if verify_ssl is not None:
            instance.verify_ssl = verify_ssl
        if auto_pull_enabled is not None:
            instance.auto_pull_enabled = auto_pull_enabled
        if auto_pull_schedule is not None:
            instance.auto_pull_schedule = auto_pull_schedule.strip().upper()
        if auto_pull_tag is not None:
            instance.auto_pull_tag = auto_pull_tag.strip()
        instance.save()
        return UpdateMISPInstance(misp_instance=instance, success=True, message="MISP instance updated.")


class DeleteMISPInstance(graphene.Mutation):
    """Delete a MISP instance (Admin only)."""

    class Arguments:
        id = graphene.UUID(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")
        if user.role not in ("ADMIN",) and not user.is_superuser:
            raise GraphQLError("Permission denied. Admin role required.")
        try:
            instance = MISPInstance.objects.get(pk=id, organization=user.organization)
        except MISPInstance.DoesNotExist:
            return DeleteMISPInstance(success=False, message="MISP instance not found.")
        instance.delete()
        return DeleteMISPInstance(success=True, message="MISP instance deleted.")


class StartOpentidePreviewTask(graphene.Mutation):
    """Create an async OpenTIDE preview task and publish it to RabbitMQ for background processing."""

    class Arguments:
        playbook_id = graphene.UUID(required=True)
        use_ai_enrichment = graphene.Boolean(default_value=False)
        force_bdr_generation = graphene.Boolean(default_value=False)

    task_id = graphene.UUID(description="Task ID to poll with opentidePreviewStatus")
    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, playbook_id, use_ai_enrichment=False, force_bdr_generation=False):
        from playbooks.models import PlaybookGraph, OpentidePreviewTask
        from core.rabbitmq import publish_event

        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")

        try:
            playbook = PlaybookGraph.objects.get(pk=playbook_id, organization=user.organization)
        except PlaybookGraph.DoesNotExist:
            return StartOpentidePreviewTask(
                task_id=None, success=False, message="Playbook not found."
            )

        task = OpentidePreviewTask.objects.create(
            playbook=playbook,
            user=user,
            use_ai_enrichment=use_ai_enrichment,
            force_bdr_generation=force_bdr_generation,
        )

        published = publish_event('opentide.preview.requested', {
            'task_id': str(task.id),
            'playbook_id': str(playbook.id),
            'user_id': str(user.id),
            'use_ai_enrichment': use_ai_enrichment,
            'force_bdr_generation': force_bdr_generation,
        })

        if not published:
            logger.warning("Failed to publish opentide.preview.requested for task %s; worker will not process.", task.id)

        return StartOpentidePreviewTask(
            task_id=task.id,
            success=True,
            message="Preview task created. Poll opentidePreviewStatus for results.",
        )


class SetOpenTidePublishProfile(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=False)
        name = graphene.String(required=True)
        repository_id = graphene.ID(required=True)
        branch = graphene.String(required=False)
        target_folder = graphene.String(required=False)
        push_platform_rules = graphene.Boolean(required=False)
        enabled_platforms = graphene.List(graphene.String, required=False)
        use_graph_configured_platforms = graphene.Boolean(required=False)
        kql_target_policy = graphene.String(required=False)
        enabled = graphene.Boolean(required=False)

    success = graphene.Boolean()
    message = graphene.String()
    profile = graphene.Field(OpenTidePublishProfileType)

    @staticmethod
    def mutate(root, info, name, repository_id, id=None, branch=None, target_folder=None, push_platform_rules=None, enabled_platforms=None, use_graph_configured_platforms=None, kql_target_policy=None, enabled=None):
        from identity.decorators import Roles
        from rules.models import RuleRepository

        user = info.context.user
        if user.is_anonymous:
            raise Exception('Authentication required')
        if user.role not in (Roles.ADMIN,) and not user.is_superuser and not user.is_staff:
            raise Exception('Only organisation admins can manage HEF publish profiles')

        try:
            repository = RuleRepository.objects.get(pk=repository_id, organization=user.organization)
        except RuleRepository.DoesNotExist:
            raise Exception('Repository not found or you do not have permission')

        if id:
            try:
                profile = OpenTidePublishProfile.objects.get(pk=id, organization=user.organization)
            except OpenTidePublishProfile.DoesNotExist:
                raise Exception('Publish profile not found')
        else:
            profile = OpenTidePublishProfile(organization=user.organization, created_by=user)

        profile.name = name
        profile.repository = repository
        if branch is not None:
            profile.branch = branch
        if target_folder is not None:
            profile.target_folder = target_folder
        if push_platform_rules is not None:
            profile.push_platform_rules = push_platform_rules
        if enabled_platforms is not None:
            profile.enabled_platforms = [p.lower() for p in enabled_platforms]
        if use_graph_configured_platforms is not None:
            profile.use_graph_configured_platforms = use_graph_configured_platforms
        if kql_target_policy is not None:
            normalized_policy = str(kql_target_policy or '').strip().lower()
            if normalized_policy not in KQL_TARGET_POLICIES:
                raise Exception(
                    f"Unsupported kql_target_policy '{kql_target_policy}'. "
                    f"Valid values: {', '.join(sorted(KQL_TARGET_POLICIES))}"
                )
            profile.kql_target_policy = normalized_policy
        if enabled is not None:
            profile.enabled = enabled
        profile.save()

        return SetOpenTidePublishProfile(success=True, message='HEF publish profile saved', profile=profile)


class DeleteOpenTidePublishProfile(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    def mutate(root, info, id):
        from identity.decorators import Roles

        user = info.context.user
        if user.is_anonymous:
            raise Exception('Authentication required')
        if user.role not in (Roles.ADMIN,) and not user.is_superuser and not user.is_staff:
            raise Exception('Only organisation admins can manage HEF publish profiles')

        deleted, _ = OpenTidePublishProfile.objects.filter(pk=id, organization=user.organization).delete()
        if not deleted:
            return DeleteOpenTidePublishProfile(success=False, message='Publish profile not found')
        return DeleteOpenTidePublishProfile(success=True, message='HEF publish profile deleted')


class PublishWorkbenchOpenTide(graphene.Mutation):
    class Arguments:
        graph_id = graphene.UUID(required=True)
        profile_id = graphene.UUID(required=False)
        repository_id = graphene.ID(required=False)
        branch = graphene.String(required=False)
        target_folder = graphene.String(required=False)
        platforms = graphene.List(graphene.String, required=False)
        commit_message = graphene.String(required=False)
        push_opentide_bundle = graphene.Boolean(required=False)
        push_platform_rules = graphene.Boolean(required=False)
        kql_target_policy = graphene.String(
            required=False,
            description="How 'kql' targets are mapped: defender, sentinel, or both.",
        )

    success = graphene.Boolean()
    message = graphene.String()
    task_id = graphene.String()

    @staticmethod
    def mutate(root, info, graph_id, profile_id=None, repository_id=None, branch=None, target_folder=None, platforms=None, commit_message=None, push_opentide_bundle=None, push_platform_rules=None, kql_target_policy=None):
        from core.rabbitmq import publish_event
        from identity.decorators import Roles
        from playbooks.models import PlaybookGraph
        from rules.models import RuleRepository

        user = info.context.user
        if user.is_anonymous:
            logger.warning('HEF publish rejected: anonymous user graph_id=%s', graph_id)
            raise GraphQLError('Authentication required')
        if user.role not in (Roles.ADMIN, Roles.ANALYST) and not user.is_superuser and not user.is_staff:
            logger.warning(
                'HEF publish rejected: insufficient role user_id=%s role=%s graph_id=%s',
                getattr(user, 'id', None),
                getattr(user, 'role', None),
                graph_id,
            )
            raise GraphQLError('Permission denied')

        logger.info(
            'HEF publish request: graph_id=%s user_id=%s org_id=%s profile_id=%s repository_id=%s branch=%s target_folder=%s platforms=%s',
            graph_id,
            getattr(user, 'id', None),
            getattr(getattr(user, 'organization', None), 'id', None),
            profile_id,
            repository_id,
            branch,
            target_folder,
            platforms,
        )

        try:
            graph = PlaybookGraph.objects.prefetch_related('linked_rules').get(pk=graph_id, organization=user.organization)
        except PlaybookGraph.DoesNotExist:
            logger.warning(
                'HEF publish rejected: workbench not found graph_id=%s user_id=%s org_id=%s',
                graph_id,
                getattr(user, 'id', None),
                getattr(getattr(user, 'organization', None), 'id', None),
            )
            return PublishWorkbenchOpenTide(success=False, message='Workbench not found', task_id=None)

        allowed_statuses = {'APPROVED', 'DEPLOYED'}
        if (graph.status or '').upper() not in allowed_statuses:
            logger.warning(
                'HEF publish rejected: invalid status graph_id=%s status=%s',
                graph_id,
                graph.status,
            )
            return PublishWorkbenchOpenTide(success=False, message='Only APPROVED or DEPLOYED workbenches can be published via OpenTIDE HEF', task_id=None)

        supported_formats = {'KQL', 'SPL', 'WAZUH', 'ELASTIC', 'EQL'}
        has_detection = graph.linked_rules.filter(format__in=supported_formats).exclude(raw_content='').exclude(raw_content__isnull=True).exists()
        if not has_detection:
            logger.warning('HEF publish rejected: no eligible linked rules graph_id=%s', graph_id)
            return PublishWorkbenchOpenTide(success=False, message='No linked detection rules found for HEF publish', task_id=None)

        profile = None
        repository = None
        if profile_id:
            try:
                profile = OpenTidePublishProfile.objects.select_related('repository').get(pk=profile_id, organization=user.organization, enabled=True)
            except OpenTidePublishProfile.DoesNotExist:
                logger.warning('HEF publish rejected: profile not found profile_id=%s graph_id=%s', profile_id, graph_id)
                return PublishWorkbenchOpenTide(success=False, message='Publish profile not found', task_id=None)
            repository = profile.repository

        if repository is None and repository_id:
            try:
                repository = RuleRepository.objects.get(pk=repository_id, organization=user.organization)
            except RuleRepository.DoesNotExist:
                logger.warning('HEF publish rejected: repository not found repository_id=%s graph_id=%s', repository_id, graph_id)
                return PublishWorkbenchOpenTide(success=False, message='Repository not found', task_id=None)

        if repository is None:
            logger.warning('HEF publish rejected: no repository resolved graph_id=%s profile_id=%s repository_id=%s', graph_id, profile_id, repository_id)
            return PublishWorkbenchOpenTide(success=False, message='A repository or publish profile is required', task_id=None)

        if not repository.git_url:
            logger.warning('HEF publish rejected: repository missing URL repo_id=%s', repository.id)
            return PublishWorkbenchOpenTide(success=False, message='Selected repository has no git URL configured', task_id=None)
        if not repository.token:
            logger.warning('HEF publish rejected: repository missing token repo_id=%s', repository.id)
            return PublishWorkbenchOpenTide(success=False, message='Selected repository has no access token configured', task_id=None)

        effective_kql_target_policy = str(kql_target_policy or '').strip().lower()
        if not effective_kql_target_policy:
            effective_kql_target_policy = (
                str(getattr(profile, 'kql_target_policy', '') or '').strip().lower()
                if profile is not None
                else 'defender'
            )
        if effective_kql_target_policy not in KQL_TARGET_POLICIES:
            effective_kql_target_policy = 'defender'

        requested_platforms = [p.lower() for p in (platforms or []) if p]
        if platforms is None and not requested_platforms and profile and profile.enabled_platforms:
            requested_platforms = [p.lower() for p in (profile.enabled_platforms or []) if p]
        if platforms is None and not requested_platforms and ((profile and profile.use_graph_configured_platforms) or not profile):
            requested_platforms = [p.lower() for p in (graph.configured_platforms or []) if p]
        requested_platforms, dropped_platforms = normalize_deployment_platforms(
            requested_platforms,
            kql_target_policy=effective_kql_target_policy,
        )
        if dropped_platforms:
            logger.warning(
                'HEF publish platform normalization dropped values: graph_id=%s dropped=%s',
                graph_id,
                dropped_platforms,
            )
        if platforms and not requested_platforms:
            return PublishWorkbenchOpenTide(
                success=False,
                message=f"Unsupported deployment platform(s): {', '.join(dropped_platforms or platforms)}",
                task_id=None,
            )

        if requested_platforms:
            configured_creds = set(
                PlatformCredential.objects.filter(
                    organization=user.organization,
                    platform__in=requested_platforms,
                    enabled=True,
                ).values_list('platform', flat=True)
            )
            missing = [platform for platform in requested_platforms if platform not in configured_creds]
            if missing:
                logger.warning('HEF publish rejected: missing credentials graph_id=%s missing=%s', graph_id, missing)
                return PublishWorkbenchOpenTide(success=False, message=f"Missing enabled platform credentials for: {', '.join(missing)}", task_id=None)

        final_branch = branch or (profile.branch if profile else None) or 'main'
        final_target_folder = target_folder if target_folder is not None else (profile.target_folder if profile else '')
        final_commit_message = commit_message or f'Publish OpenTIDE HEF package: {graph.title}'
        final_push_opentide_bundle = True if push_opentide_bundle is None else push_opentide_bundle
        final_push_platform_rules = (
            profile.push_platform_rules
            if push_platform_rules is None and profile is not None
            else bool(push_platform_rules)
        )

        if not final_push_opentide_bundle and not final_push_platform_rules:
            return PublishWorkbenchOpenTide(
                success=False,
                message='Select at least one repository publish option: OpenTIDE bundle or individual rules.',
                task_id=None,
            )

        job = OpenTideHefPublishJob.objects.create(
            playbook=graph,
            user=user,
            organization=user.organization,
            profile=profile,
            repository=repository,
            status='QUEUED',
            commit_message=final_commit_message,
            branch=final_branch,
            target_folder=final_target_folder or '',
            push_opentide_bundle=final_push_opentide_bundle,
            push_platform_rules=final_push_platform_rules,
            requested_platforms=requested_platforms,
        )

        logger.info(
            'HEF publish job created: task_id=%s graph_id=%s repository_id=%s requested_platforms=%s',
            job.id,
            graph.id,
            repository.id if repository else None,
            requested_platforms,
        )

        published = publish_event(
            'opentide.hef.publish.queued',
            {
                'task_id': str(job.id),
                'playbook_id': str(graph.id),
                'organization_id': str(user.organization.id),
                'user_id': str(user.id),
            },
        )
        if not published:
            job.status = 'FAILED'
            job.error_message = 'Failed to queue HEF publish job: RabbitMQ unavailable.'
            job.save(update_fields=['status', 'error_message'])
            logger.error('HEF publish enqueue failed: task_id=%s graph_id=%s', job.id, graph.id)
            return PublishWorkbenchOpenTide(success=False, message='Failed to queue HEF publish job: RabbitMQ unavailable.', task_id=str(job.id))

        logger.info('HEF publish enqueued: task_id=%s graph_id=%s platforms=%s', job.id, graph.id, requested_platforms)
        if requested_platforms:
            success_message = (
                'OpenTIDE HEF publish queued for background processing. '
                f'Deployment targets: {", ".join(requested_platforms)}.'
            )
        else:
            success_message = (
                'OpenTIDE HEF publish queued for background processing. '
                'No deployment targets selected (repository publish only).'
            )
        return PublishWorkbenchOpenTide(success=True, message=success_message, task_id=str(job.id))


class SetPlatformCredential(graphene.Mutation):
    """
    Create or update API credentials for a SIEM/EDR platform.

    Credential values are stored encrypted using Fernet symmetric encryption.
    Existing credentials for the same (organisation, platform) pair are replaced.
    """

    class Arguments:
        platform = graphene.String(
            required=True,
            description="Platform key: defender, sentinel, splunk, qradar, or wazuh",
        )
        profile_name = graphene.String(
            required=False,
            description="Optional credential profile name. Defaults to 'default'.",
        )
        credentials = graphene.JSONString(
            required=True,
            description="JSON object containing the platform credentials (e.g. {tenant_id, client_id, …})",
        )
        enabled = graphene.Boolean(default_value=True)
        set_default = graphene.Boolean(
            required=False,
            description="When true, mark this profile as the default for the platform.",
        )

    credential = graphene.Field(PlatformCredentialType)
    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    def mutate(root, info, platform, credentials, enabled=True, profile_name='default', set_default=False):
        import json as _json
        from django.db import transaction
        from identity.decorators import role_required, Roles

        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        if user.role not in (Roles.ADMIN,) and not user.is_superuser and not user.is_staff:
            raise Exception("Only organisation admins can manage platform credentials")

        valid_platforms = {'defender', 'sentinel', 'splunk', 'qradar', 'wazuh'}
        if platform not in valid_platforms:
            raise Exception(f"Unknown platform '{platform}'. Valid values: {', '.join(sorted(valid_platforms))}")
        normalized_profile = str(profile_name or 'default').strip() or 'default'

        # Parse credentials JSON string if needed
        if isinstance(credentials, str):
            try:
                cred_dict = _json.loads(credentials)
            except ValueError as exc:
                raise Exception(f"Invalid credentials JSON: {exc}")
        else:
            cred_dict = credentials

        with transaction.atomic():
            cred, created = PlatformCredential.objects.get_or_create(
                organization=user.organization,
                platform=platform,
                profile_name=normalized_profile,
                defaults={'enabled': enabled},
            )
            cred.credentials = cred_dict
            cred.enabled = enabled
            # First profile for this org+platform should become default automatically.
            first_profile = not PlatformCredential.objects.filter(
                organization=user.organization,
                platform=platform,
            ).exclude(pk=cred.pk).exists()
            if set_default or first_profile:
                PlatformCredential.objects.filter(
                    organization=user.organization,
                    platform=platform,
                ).exclude(pk=cred.pk).update(is_default=False)
                cred.is_default = True
            cred.save()

        action = 'created' if created else 'updated'
        return SetPlatformCredential(
            credential=cred,
            success=True,
            message=f"Platform credentials {action} successfully for {platform} (profile: {normalized_profile})",
        )


class DeletePlatformCredential(graphene.Mutation):
    """Delete stored API credentials for a SIEM/EDR platform."""

    class Arguments:
        platform = graphene.String(required=True)
        profile_name = graphene.String(required=False)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    def mutate(root, info, platform, profile_name=None):
        from identity.decorators import Roles

        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        if user.role not in (Roles.ADMIN,) and not user.is_superuser and not user.is_staff:
            raise Exception("Only organisation admins can manage platform credentials")

        target = None
        if profile_name:
            target = PlatformCredential.objects.filter(
                organization=user.organization,
                platform=platform,
                profile_name=str(profile_name).strip(),
            ).first()
        else:
            target = PlatformCredential.get_preferred_for_platform(
                organization=user.organization,
                platform=platform,
                profile_name='default',
            )

        if not target:
            return DeletePlatformCredential(success=False, message=f"No credentials found for {platform}")

        deleted_profile = target.profile_name
        was_default = bool(target.is_default)
        target.delete()

        if was_default:
            replacement = PlatformCredential.get_preferred_for_platform(
                organization=user.organization,
                platform=platform,
            )
            if replacement and not replacement.is_default:
                replacement.is_default = True
                replacement.save(update_fields=['is_default', 'updated_at'])

        return DeletePlatformCredential(
            success=True,
            message=f"Credentials for {platform} deleted (profile: {deleted_profile})",
        )


class TestPlatformConnection(graphene.Mutation):
    """Test connectivity to a configured SIEM/EDR platform."""

    class Arguments:
        platform = graphene.String(required=True)
        profile_name = graphene.String(required=False)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    def mutate(root, info, platform, profile_name=None):
        import logging
        from identity.decorators import Roles

        logger = logging.getLogger(__name__)
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        if user.role not in (Roles.ADMIN,) and not user.is_superuser and not user.is_staff:
            raise Exception("Only organisation admins can test platform connections")

        credential = PlatformCredential.get_preferred_for_platform(
            organization=user.organization,
            platform=platform,
            profile_name=profile_name,
        )
        if not credential:
            return TestPlatformConnection(
                success=False,
                message="Platform credentials not configured",
            )

        try:
            success, message = credential.test_connection()
            return TestPlatformConnection(success=success, message=message)
        except Exception as exc:
            logger.error("Connection test failed for %s: %s", platform, exc)
            return TestPlatformConnection(success=False, message=f"Test failed: {exc}")


class UpdateDacDeploymentConfig(graphene.Mutation):
    class Arguments:
        mode = graphene.String(required=True)
        target_repository_id = graphene.ID(required=False)
        target_branch = graphene.String(required=False)
        target_folder = graphene.String(required=False)
        target_platforms = graphene.List(graphene.String, required=False)
        publish_profile_id = graphene.UUID(required=False)

    success = graphene.Boolean()
    message = graphene.String()
    config = graphene.Field(DacDeploymentConfigType)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(
        root,
        info,
        mode,
        target_repository_id=None,
        target_branch=None,
        target_folder=None,
        target_platforms=None,
        publish_profile_id=None,
    ):
        from rules.models import RuleRepository

        user = info.context.user
        normalized_mode = str(mode or '').strip().upper()
        allowed_modes = {choice for choice, _label in DacDeploymentConfig.Mode.choices}
        if normalized_mode not in allowed_modes:
            raise GraphQLError(
                f"Invalid mode '{mode}'. Valid values: {', '.join(sorted(allowed_modes))}"
            )

        config, _ = DacDeploymentConfig.objects.get_or_create(
            organization=user.organization,
            defaults={'updated_by': user},
        )

        ignores_github_targets = normalized_mode == DacDeploymentConfig.Mode.DEPLOY_ONLY

        if target_repository_id and not ignores_github_targets:
            try:
                config.target_repository = RuleRepository.objects.get(
                    pk=target_repository_id,
                    organization=user.organization,
                )
            except RuleRepository.DoesNotExist:
                raise GraphQLError('Repository not found or you do not have permission')

        if publish_profile_id and not ignores_github_targets:
            try:
                config.publish_profile = OpenTidePublishProfile.objects.get(
                    pk=publish_profile_id,
                    organization=user.organization,
                )
            except OpenTidePublishProfile.DoesNotExist:
                raise GraphQLError('Publish profile not found')

        if target_branch is not None:
            config.target_branch = (target_branch or 'main').strip() or 'main'
        elif not config.target_branch:
            config.target_branch = 'main'

        if target_folder is not None:
            config.target_folder = target_folder.strip()

        normalized_platforms = config.target_platforms or []
        if target_platforms is not None:
            normalized_platforms = []
            for platform in target_platforms:
                value = str(platform or '').strip().lower()
                if not value:
                    continue
                if value not in PLATFORM_DEPLOYER_MAP:
                    raise GraphQLError(f"Unsupported deployment platform '{platform}'.")
                normalized_platforms.append(value)
            normalized_platforms = list(dict.fromkeys(normalized_platforms))

        if normalized_mode in (
            DacDeploymentConfig.Mode.GIT_PUSH,
            DacDeploymentConfig.Mode.GIT_PUSH_AND_DEPLOY,
        ) and not config.target_repository:
            raise GraphQLError(
                'Target repository is required for GIT_PUSH and GIT_PUSH_AND_DEPLOY modes'
            )

        if normalized_mode in (
            DacDeploymentConfig.Mode.GIT_PUSH_AND_DEPLOY,
            DacDeploymentConfig.Mode.DEPLOY_ONLY,
        ) and not normalized_platforms:
            raise GraphQLError(
                'Target platforms are required for GIT_PUSH_AND_DEPLOY and DEPLOY_ONLY modes'
            )

        if normalized_mode == DacDeploymentConfig.Mode.DEPLOY_ONLY:
            config.target_repository = None
            config.target_branch = 'main'
            config.target_folder = ''
            config.publish_profile = None
        elif normalized_mode != DacDeploymentConfig.Mode.GIT_PUSH_AND_DEPLOY:
            normalized_platforms = []

        config.mode = normalized_mode
        config.target_platforms = normalized_platforms
        config.updated_by = user
        config.save()

        return UpdateDacDeploymentConfig(
            success=True,
            message='DaC deployment configuration saved',
            config=config,
        )


class UpsertSmtpSettings(graphene.Mutation):
    class Arguments:
        smtp_server = graphene.String(required=True)
        smtp_port = graphene.Int(required=True)
        encryption = graphene.String(required=True)
        login_method = graphene.String(required=True)
        smtp_username = graphene.String(required=False)
        smtp_password = graphene.String(required=False)
        from_email = graphene.String(required=False)
        organization_id = graphene.UUID(required=False)

    success = graphene.Boolean()
    message = graphene.String()
    smtp_settings = graphene.Field(SmtpSettingsType)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(
        root,
        info,
        smtp_server,
        smtp_port,
        encryption,
        login_method,
        smtp_username=None,
        smtp_password=None,
        from_email=None,
        organization_id=None,
    ):
        from django.core.exceptions import ValidationError

        user = info.context.user
        target_org = user.organization
        if organization_id is not None:
            if not (user.is_superuser or user.is_staff):
                raise GraphQLError('Only superusers can update SMTP settings for other organizations.')
            try:
                target_org = Organization.objects.get(pk=organization_id)
            except Organization.DoesNotExist:
                raise GraphQLError('Organization not found')

        org_settings, _ = OrganizationSmtpSettings.objects.select_related('shared_profile').get_or_create(
            organization=target_org
        )
        if org_settings.enforce_shared and not (user.is_superuser or user.is_staff):
            raise GraphQLError(
                'SMTP override is locked by superuser for this organization. '
                'Ask a platform admin to unlock or update the shared profile.'
            )

        normalized_encryption = str(encryption or '').strip().upper()
        normalized_login_method = str(login_method or '').strip().upper()
        allowed_encryption = {choice for choice, _ in SharedSmtpProfile.Encryption.choices}
        allowed_login_methods = {choice for choice, _ in SharedSmtpProfile.LoginMethod.choices}

        if normalized_encryption not in allowed_encryption:
            raise GraphQLError(
                f"Invalid encryption '{encryption}'. Valid values: {', '.join(sorted(allowed_encryption))}"
            )
        if normalized_login_method not in allowed_login_methods:
            raise GraphQLError(
                f"Invalid login method '{login_method}'. Valid values: {', '.join(sorted(allowed_login_methods))}"
            )

        org_settings.custom_enabled = True
        org_settings.custom_smtp_server = (smtp_server or '').strip()
        org_settings.custom_smtp_port = int(smtp_port)
        org_settings.custom_encryption = normalized_encryption
        org_settings.custom_login_method = normalized_login_method

        if smtp_username is not None:
            org_settings.custom_smtp_username = smtp_username.strip()
        elif normalized_login_method == SharedSmtpProfile.LoginMethod.PLAIN:
            org_settings.custom_smtp_username = ''

        if smtp_password is not None:
            org_settings.custom_smtp_password = smtp_password
        elif normalized_login_method == SharedSmtpProfile.LoginMethod.PLAIN:
            org_settings.custom_smtp_password = ''

        if from_email is not None:
            org_settings.custom_from_email = from_email.strip()

        org_settings.updated_by = user

        try:
            org_settings.save()
        except ValidationError as exc:
            details = getattr(exc, 'message_dict', None) or {'error': exc.messages}
            raise GraphQLError(str(details))

        effective = get_effective_smtp_for_organization(target_org, create_if_missing=False)
        return UpsertSmtpSettings(
            success=True,
            message='Organization SMTP settings updated successfully.',
            smtp_settings=effective,
        )


class SetSharedSmtpProfile(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=False)
        name = graphene.String(required=False)
        smtp_server = graphene.String(required=True)
        smtp_port = graphene.Int(required=True)
        encryption = graphene.String(required=True)
        login_method = graphene.String(required=True)
        smtp_username = graphene.String(required=False)
        smtp_password = graphene.String(required=False)
        from_email = graphene.String(required=False)
        is_active = graphene.Boolean(required=False)

    success = graphene.Boolean()
    message = graphene.String()
    profile = graphene.Field(SharedSmtpProfileType)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(
        root,
        info,
        smtp_server,
        smtp_port,
        encryption,
        login_method,
        id=None,
        name=None,
        smtp_username=None,
        smtp_password=None,
        from_email=None,
        is_active=None,
    ):
        from django.core.exceptions import ValidationError

        user = info.context.user
        if not (user.is_superuser or user.is_staff):
            raise GraphQLError('Permission denied. Superuser access required.')

        normalized_encryption = str(encryption or '').strip().upper()
        normalized_login_method = str(login_method or '').strip().upper()
        allowed_encryption = {choice for choice, _ in SharedSmtpProfile.Encryption.choices}
        allowed_login_methods = {choice for choice, _ in SharedSmtpProfile.LoginMethod.choices}

        if normalized_encryption not in allowed_encryption:
            raise GraphQLError(
                f"Invalid encryption '{encryption}'. Valid values: {', '.join(sorted(allowed_encryption))}"
            )
        if normalized_login_method not in allowed_login_methods:
            raise GraphQLError(
                f"Invalid login method '{login_method}'. Valid values: {', '.join(sorted(allowed_login_methods))}"
            )

        profile = None
        created = False
        if id is not None:
            profile = SharedSmtpProfile.objects.filter(pk=id).first()
            if profile is None:
                raise GraphQLError('Shared SMTP profile not found.')
        else:
            profile = SharedSmtpProfile(created_by=user)
            created = True

        if name is not None:
            profile.name = name.strip()
        elif created:
            raise GraphQLError('Profile name is required when creating a shared SMTP profile.')

        profile.smtp_server = (smtp_server or '').strip()
        profile.smtp_port = int(smtp_port)
        profile.encryption = normalized_encryption
        profile.login_method = normalized_login_method

        if smtp_username is not None:
            profile.smtp_username = smtp_username.strip()
        elif normalized_login_method == SharedSmtpProfile.LoginMethod.PLAIN:
            profile.smtp_username = ''

        if smtp_password is not None:
            profile.smtp_password = smtp_password
        elif normalized_login_method == SharedSmtpProfile.LoginMethod.PLAIN:
            profile.smtp_password = ''

        if from_email is not None:
            profile.from_email = from_email.strip()
        if is_active is not None:
            profile.is_active = bool(is_active)

        try:
            profile.save()
        except ValidationError as exc:
            details = getattr(exc, 'message_dict', None) or {'error': exc.messages}
            raise GraphQLError(str(details))

        return SetSharedSmtpProfile(
            success=True,
            message='Shared SMTP profile created successfully.' if created else 'Shared SMTP profile updated successfully.',
            profile=profile,
        )


class DeleteSharedSmtpProfile(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, id):
        user = info.context.user
        if not (user.is_superuser or user.is_staff):
            raise GraphQLError('Permission denied. Superuser access required.')

        profile = SharedSmtpProfile.objects.filter(pk=id).first()
        if profile is None:
            return DeleteSharedSmtpProfile(success=False, message='Shared SMTP profile not found.')

        # Preserve assignment references for history; deactivate instead of hard delete.
        profile.is_active = False
        profile.save(update_fields=['is_active', 'updated_at'])
        return DeleteSharedSmtpProfile(success=True, message='Shared SMTP profile deactivated.')


class SetOrganizationSmtpPolicy(graphene.Mutation):
    class Arguments:
        organization_id = graphene.UUID(required=True)
        shared_profile_id = graphene.UUID(required=False)
        enforce_shared = graphene.Boolean(required=False)

    success = graphene.Boolean()
    message = graphene.String()
    smtp_settings = graphene.Field(SmtpSettingsType)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, organization_id, shared_profile_id=None, enforce_shared=None):
        user = info.context.user
        if not (user.is_superuser or user.is_staff):
            raise GraphQLError('Permission denied. Superuser access required.')

        try:
            target_org = Organization.objects.get(pk=organization_id)
        except Organization.DoesNotExist:
            raise GraphQLError('Organization not found')

        org_settings, _ = OrganizationSmtpSettings.objects.get_or_create(organization=target_org)

        if shared_profile_id is not None:
            if str(shared_profile_id).strip():
                profile = SharedSmtpProfile.objects.filter(pk=shared_profile_id, is_active=True).first()
                if profile is None:
                    raise GraphQLError('Shared SMTP profile not found or inactive.')
                org_settings.shared_profile = profile
            else:
                org_settings.shared_profile = None

        if enforce_shared is not None:
            org_settings.enforce_shared = bool(enforce_shared)
            if org_settings.enforce_shared and not org_settings.shared_profile_id:
                raise GraphQLError('Cannot enable enforce_shared without assigning a shared profile.')

        org_settings.updated_by = user
        org_settings.save()

        effective = get_effective_smtp_for_organization(target_org, create_if_missing=False)
        return SetOrganizationSmtpPolicy(
            success=True,
            message='Organization SMTP policy updated successfully.',
            smtp_settings=effective,
        )


class SetOrganizationSharedFlags(graphene.Mutation):
    class Arguments:
        organization_ids = graphene.List(graphene.UUID, required=True)
        smtp_shared_enabled = graphene.Boolean(required=False)
        ai_shared_enabled = graphene.Boolean(required=False)

    success = graphene.Boolean()
    message = graphene.String()
    updated_count = graphene.Int()
    organizations = graphene.List(OrganizationType)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(
        root,
        info,
        organization_ids,
        smtp_shared_enabled=None,
        ai_shared_enabled=None,
    ):
        user = info.context.user
        if not (user.is_superuser or user.is_staff):
            raise GraphQLError('Permission denied. Superuser access required.')

        if smtp_shared_enabled is None and ai_shared_enabled is None:
            raise GraphQLError('Provide at least one flag to update (smtp_shared_enabled or ai_shared_enabled).')

        normalized_ids: List[str] = []
        seen_ids: Set[str] = set()
        for raw_id in organization_ids or []:
            if raw_id is None:
                continue
            string_id = str(raw_id).strip()
            if not string_id or string_id in seen_ids:
                continue
            seen_ids.add(string_id)
            normalized_ids.append(string_id)

        if not normalized_ids:
            raise GraphQLError('At least one organization id is required.')

        org_map = {
            str(org.id): org
            for org in Organization.objects.filter(id__in=normalized_ids)
        }
        missing_ids = [oid for oid in normalized_ids if oid not in org_map]
        if missing_ids:
            raise GraphQLError(f'Organization(s) not found: {", ".join(missing_ids)}')

        smtp_profile = None
        if smtp_shared_enabled is True:
            smtp_profile = (
                SharedSmtpProfile.objects.filter(is_active=True, name__iexact='System Shared SMTP')
                .order_by('-updated_at')
                .first()
            )
            if smtp_profile is None:
                smtp_profile = (
                    SharedSmtpProfile.objects.filter(is_active=True)
                    .order_by('-updated_at', 'name')
                    .first()
                )
            if smtp_profile is None:
                raise GraphQLError(
                    'No active shared SMTP profile found. Configure the shared SMTP profile first.'
                )

        ai_profile = None
        if ai_shared_enabled is True:
            ai_profile = (
                SharedAIProfile.objects.filter(is_active=True, name__iexact='System Shared AI')
                .order_by('-updated_at')
                .first()
            )
            if ai_profile is None:
                ai_profile = (
                    SharedAIProfile.objects.filter(is_active=True)
                    .order_by('-updated_at', 'name')
                    .first()
                )
            if ai_profile is None:
                raise GraphQLError(
                    'No active shared AI profile found. Configure the shared AI profile first.'
                )

        updated_orgs: List[Organization] = []
        for org_id in normalized_ids:
            target_org = org_map[org_id]

            if smtp_shared_enabled is not None:
                smtp_settings, _ = OrganizationSmtpSettings.objects.get_or_create(
                    organization=target_org
                )
                if smtp_shared_enabled:
                    smtp_settings.shared_profile = smtp_profile
                    smtp_settings.enforce_shared = True
                else:
                    smtp_settings.enforce_shared = False
                smtp_settings.updated_by = user
                smtp_settings.save()

            if ai_shared_enabled is not None:
                ai_settings, _ = OrgAISettings.objects.get_or_create(organization=target_org)
                if ai_shared_enabled:
                    ai_settings.shared_profile = ai_profile
                    ai_settings.shared_profile_locked = True
                else:
                    ai_settings.shared_profile_locked = False
                ai_settings.save()

            updated_orgs.append(target_org)

        return SetOrganizationSharedFlags(
            success=True,
            message='Organization shared profile flags updated successfully.',
            updated_count=len(updated_orgs),
            organizations=updated_orgs,
        )


class SetHefaistosRemotePeer(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=False)
        name = graphene.String(required=True)
        remote_url = graphene.String(required=True)
        remote_instance_id = graphene.UUID(required=True)
        api_key = graphene.String(required=False)
        default_scope = graphene.String(required=False, default_value='ALL')
        auto_pull_enabled = graphene.Boolean(required=False)
        auto_pull_schedule = graphene.String(required=False)
        verify_ssl = graphene.Boolean(required=False, default_value=True)
        allow_self_signed = graphene.Boolean(required=False, default_value=False)
        tls_cert_fingerprint = graphene.String(required=False)
        enabled = graphene.Boolean(required=False, default_value=True)

    success = graphene.Boolean()
    message = graphene.String()
    peer = graphene.Field(HefaistosRemotePeerType)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(
        root,
        info,
        name,
        remote_url,
        remote_instance_id,
        id=None,
        api_key=None,
        default_scope='ALL',
        auto_pull_enabled=None,
        auto_pull_schedule=None,
        verify_ssl=True,
        allow_self_signed=False,
        tls_cert_fingerprint=None,
        enabled=True,
    ):
        from django.core.exceptions import ValidationError

        user = info.context.user
        normalized_scope = normalize_scope(default_scope)

        peer = None
        created = False
        if id:
            peer = HefaistosRemotePeer.objects.filter(pk=id, organization=user.organization).first()
            if peer is None:
                raise GraphQLError('Remote peer not found')
        else:
            peer = HefaistosRemotePeer(
                organization=user.organization,
                created_by=user,
            )
            created = True

        previous_auto_pull_enabled = bool(getattr(peer, 'auto_pull_enabled', False))
        previous_auto_pull_schedule = str(getattr(peer, 'auto_pull_schedule', 'DAILY') or 'DAILY').upper()
        previous_next_auto_pull_at = getattr(peer, 'next_auto_pull_at', None)

        peer.name = (name or '').strip()
        peer.remote_url = (remote_url or '').strip().rstrip('/')
        peer.remote_instance_id = remote_instance_id
        peer.default_scope = normalized_scope
        if auto_pull_enabled is not None:
            peer.auto_pull_enabled = bool(auto_pull_enabled)
        if auto_pull_schedule is not None:
            peer.auto_pull_schedule = normalize_auto_pull_schedule(auto_pull_schedule)
        else:
            peer.auto_pull_schedule = normalize_auto_pull_schedule(getattr(peer, 'auto_pull_schedule', 'DAILY'))
        peer.verify_ssl = bool(verify_ssl)
        peer.allow_self_signed = bool(allow_self_signed)
        peer.tls_cert_fingerprint = (tls_cert_fingerprint or '').strip()
        peer.enabled = bool(enabled)
        if api_key is not None and str(api_key).strip():
            peer.api_key = str(api_key).strip()

        if peer.auto_pull_enabled:
            auto_schedule_changed = previous_auto_pull_schedule != peer.auto_pull_schedule
            should_initialize_next_run = (
                created
                or not previous_auto_pull_enabled
                or auto_schedule_changed
                or previous_next_auto_pull_at is None
            )
            if should_initialize_next_run:
                peer.next_auto_pull_at = compute_next_auto_pull_at(peer.auto_pull_schedule)
        else:
            peer.next_auto_pull_at = None

        try:
            peer.full_clean()
            peer.save()
        except ValidationError as exc:
            details = getattr(exc, 'message_dict', None) or {'error': exc.messages}
            raise GraphQLError(str(details))

        return SetHefaistosRemotePeer(
            success=True,
            message='Remote peer created successfully' if created else 'Remote peer updated successfully',
            peer=peer,
        )


class DeleteHefaistosRemotePeer(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, id):
        user = info.context.user
        deleted, _ = HefaistosRemotePeer.objects.filter(
            pk=id,
            organization=user.organization,
        ).delete()
        if not deleted:
            return DeleteHefaistosRemotePeer(success=False, message='Remote peer not found')
        return DeleteHefaistosRemotePeer(success=True, message='Remote peer deleted')


class CreateHefaistosInboundShareKey(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        allowed_scopes = graphene.List(graphene.String, required=True)
        enforce_tag_filter = graphene.Boolean(required=False, default_value=False)
        required_tags = graphene.List(graphene.String, required=False)
        expires_at = graphene.DateTime(required=False)

    success = graphene.Boolean()
    message = graphene.String()
    key = graphene.Field(HefaistosInboundShareKeyType)
    raw_api_key = graphene.String()

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(
        root,
        info,
        name,
        allowed_scopes,
        enforce_tag_filter=False,
        required_tags=None,
        expires_at=None,
    ):
        from django.core.exceptions import ValidationError

        user = info.context.user
        scopes = [normalize_scope(scope) for scope in (allowed_scopes or [])]
        if not scopes:
            raise GraphQLError('At least one scope is required')
        if 'ALL' in scopes:
            scopes = ['ALL']
        else:
            scopes = list(dict.fromkeys(scopes))

        normalized_tags = normalize_required_tags(required_tags)
        raw_key = generate_raw_share_key()
        entry = HefaistosInboundShareKey(
            organization=user.organization,
            name=(name or '').strip(),
            key_hash=hash_api_key(raw_key),
            key_hint=build_key_hint(raw_key),
            allowed_scopes=scopes,
            enforce_tag_filter=bool(enforce_tag_filter),
            required_tags=normalized_tags,
            expires_at=expires_at,
            is_active=True,
            created_by=user,
        )
        try:
            entry.full_clean()
            entry.save()
        except ValidationError as exc:
            details = getattr(exc, 'message_dict', None) or {'error': exc.messages}
            raise GraphQLError(str(details))

        return CreateHefaistosInboundShareKey(
            success=True,
            message='Inbound share key created. Store the key now; it will not be shown again.',
            key=entry,
            raw_api_key=raw_key,
        )


class RevokeHefaistosInboundShareKey(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)

    success = graphene.Boolean()
    message = graphene.String()
    key = graphene.Field(HefaistosInboundShareKeyType)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, id):
        user = info.context.user
        key_obj = HefaistosInboundShareKey.objects.filter(
            pk=id,
            organization=user.organization,
        ).first()
        if key_obj is None:
            return RevokeHefaistosInboundShareKey(success=False, message='Share key not found', key=None)
        key_obj.is_active = False
        key_obj.save(update_fields=['is_active', 'updated_at'])
        return RevokeHefaistosInboundShareKey(success=True, message='Share key revoked', key=key_obj)


class PullFromRemoteHefaistos(graphene.Mutation):
    class Arguments:
        peer_id = graphene.UUID(required=True)
        scope = graphene.String(required=False)

    success = graphene.Boolean()
    message = graphene.String()
    job = graphene.Field(HefaistosPullJobType)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, peer_id, scope=None):
        user = info.context.user
        peer = HefaistosRemotePeer.objects.filter(
            pk=peer_id,
            organization=user.organization,
        ).first()
        if peer is None:
            return PullFromRemoteHefaistos(success=False, message='Remote peer not found', job=None)
        if not peer.enabled:
            return PullFromRemoteHefaistos(success=False, message='Remote peer is disabled', job=None)

        try:
            if scope:
                normalize_scope(scope)
            job = pull_from_remote_peer(peer, actor=user, requested_scope=scope or peer.default_scope)
            return PullFromRemoteHefaistos(
                success=True,
                message=job.message or 'Pull completed',
                job=job,
            )
        except Exception as exc:
            # pull_from_remote_peer already records a FAILED job entry
            return PullFromRemoteHefaistos(success=False, message=str(exc), job=None)


class SetOrgAiTaskConfig(graphene.Mutation):
    class Arguments:
        task_key = graphene.String(required=True)
        enabled = graphene.Boolean(required=False)
        schedule = graphene.String(required=False)
        day_of_week = graphene.Int(required=False)
        day_of_month = graphene.Int(required=False)
        run_hour = graphene.Int(required=False)
        run_minute = graphene.Int(required=False)

    success = graphene.Boolean()
    message = graphene.String()
    config = graphene.Field(OrgAITaskConfigType)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(
        root,
        info,
        task_key,
        enabled=None,
        schedule=None,
        day_of_week=None,
        day_of_month=None,
        run_hour=None,
        run_minute=None,
    ):
        user = info.context.user
        task = get_ai_task_definition(task_key)
        if not task:
            raise GraphQLError(f"Unknown AI task key '{task_key}'")

        config = get_or_create_task_config(
            user.organization,
            task_key=task_key,
            updated_by=user,
        )
        try:
            updated = update_task_config(
                config,
                enabled=enabled,
                schedule=schedule,
                day_of_week=day_of_week,
                day_of_month=day_of_month,
                run_hour=run_hour,
                run_minute=run_minute,
                updated_by=user,
            )
        except ValueError as exc:
            raise GraphQLError(str(exc))

        return SetOrgAiTaskConfig(
            success=True,
            message='AI task configuration saved',
            config=updated,
        )


class RunOrgAiTaskNow(graphene.Mutation):
    class Arguments:
        task_key = graphene.String(required=True)

    success = graphene.Boolean()
    message = graphene.String()
    run = graphene.Field(OrgAITaskRunType)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, task_key):
        user = info.context.user
        task = get_ai_task_definition(task_key)
        if not task:
            raise GraphQLError(f"Unknown AI task key '{task_key}'")

        run = run_task_now(
            user.organization,
            task_key=task_key,
            actor=user,
        )
        success = run.status != OrganizationAITaskRun.Status.FAILED
        return RunOrgAiTaskNow(
            success=success,
            message='AI task executed' if success else (run.error_message or 'AI task failed'),
            run=run,
        )


class QueueOpenTideHefImport(graphene.Mutation):
    """Enqueue an asynchronous OpenTIDE HEF import job."""

    class Arguments:
        profile_id = graphene.UUID(required=False)
        repo_owner = graphene.String(required=False)
        repo_name = graphene.String(required=False)
        branch = graphene.String(required=False)
        target_folder = graphene.String(required=False)
        commit_sha = graphene.String(required=False)
        selected_bundles = graphene.List(graphene.String, required=True)
        conflict_mode = graphene.String(required=False, default_value='NEW_COPY')
        import_platform_rules = graphene.Boolean(required=False, default_value=True)
        dry_run = graphene.Boolean(required=False, default_value=False)

    task_id = graphene.UUID()
    status = graphene.String()

    @staticmethod
    @role_required([Roles.ANALYST, Roles.ADMIN])
    def mutate(
        root,
        info,
        selected_bundles,
        profile_id=None,
        repo_owner=None,
        repo_name=None,
        branch=None,
        target_folder=None,
        commit_sha=None,
        conflict_mode='NEW_COPY',
        import_platform_rules=True,
        dry_run=False,
    ):
        import uuid as _uuid

        user = info.context.user
        org = user.organization

        valid_modes = {'NEW_COPY', 'OVERWRITE', 'SKIP'}
        conflict_mode = (conflict_mode or 'NEW_COPY').upper()
        if conflict_mode not in valid_modes:
            raise GraphQLError(f"Invalid conflict_mode '{conflict_mode}'. Valid: {valid_modes}")

        if not selected_bundles:
            raise GraphQLError('At least one bundle path must be selected.')

        max_bundles = getattr(__import__('django.conf', fromlist=['settings']).settings,
                               'HEF_IMPORT_MAX_BUNDLES_PER_JOB', 100)
        if len(selected_bundles) > max_bundles:
            raise GraphQLError(
                f'Too many bundles selected ({len(selected_bundles)}). '
                f'Maximum allowed is {max_bundles}.'
            )

        _profile = None
        _repo_owner = repo_owner
        _repo_name = repo_name
        _branch = branch or 'main'
        _target_folder = target_folder or ''

        if profile_id:
            try:
                _profile = OpenTidePublishProfile.objects.select_related('repository').get(
                    pk=profile_id, organization=org
                )
            except OpenTidePublishProfile.DoesNotExist:
                raise GraphQLError('HEF publish profile not found')
            repo = _profile.repository
            if repo:
                from playbooks.hef_publish import extract_repository_details
                details = extract_repository_details(repo.git_url)
                if details:
                    _repo_owner, _repo_name, _provider = details
            _branch = branch or _profile.branch or 'main'
            _target_folder = target_folder or _profile.target_folder or ''
        else:
            if not _repo_owner or not _repo_name:
                raise GraphQLError('Either profile_id or repo_owner + repo_name are required')
            _validate_github_component(_repo_owner, 'repo_owner')
            _validate_github_component(_repo_name, 'repo_name')

        _validate_branch(_branch)
        _validate_commit_sha(commit_sha or '')

        job = OpenTideHefImportJob.objects.create(
            organization=org,
            created_by=user,
            profile=_profile,
            repo_owner=_repo_owner or '',
            repo_name=_repo_name or '',
            branch=_branch,
            target_folder=_target_folder,
            source_commit_sha=commit_sha or '',
            selected_bundles=selected_bundles,
            conflict_mode=conflict_mode,
            import_platform_rules=import_platform_rules,
            dry_run=dry_run,
            status='QUEUED',
        )

        # Publish to RabbitMQ
        try:
            from core.rabbitmq import publish_message
            publish_message(
                routing_key='opentide.hef.import.queued',
                message={'job_id': str(job.id)},
            )
        except Exception as exc:
            logger.exception('Failed to publish HEF import job to RabbitMQ: %s', exc)
            job.status = 'FAILED'
            job.error_message = f'Failed to queue job: {exc}'
            job.save(update_fields=['status', 'error_message'])
            raise GraphQLError(f'Failed to queue import job: {exc}')

        logger.info(
            'OpenTIDE HEF import job queued: task_id=%s user_id=%s org_id=%s bundles=%d',
            job.id, user.id, org.id, len(selected_bundles),
        )

        return QueueOpenTideHefImport(task_id=job.id, status='QUEUED')


class CreateBillingAddonCheckoutSession(graphene.Mutation):
    class Arguments:
        add_extra_users = graphene.Int(required=False, default_value=0)
        add_extra_organizations = graphene.Int(required=False, default_value=0)
        success_url = graphene.String(required=False)
        cancel_url = graphene.String(required=False)

    session = graphene.Field(BillingCheckoutSessionType)
    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @role_required([Roles.ADMIN, Roles.RESOURCE_MANAGER])
    def mutate(root, info, add_extra_users=0, add_extra_organizations=0, success_url=None, cancel_url=None):
        user = info.context.user
        if not stripe_is_configured():
            return CreateBillingAddonCheckoutSession(
                success=False,
                message='Stripe billing is not configured on this instance.',
                session=None,
            )

        profile, _ = OrganizationBillingProfile.objects.get_or_create(
            organization=user.organization,
            defaults={
                'included_users': OrganizationBillingProfile.BASE_USERS,
                'included_organizations': OrganizationBillingProfile.BASE_ORGANIZATIONS,
            },
        )
        try:
            checkout_session = create_addon_checkout_session(
                billing_profile=profile,
                add_extra_users=add_extra_users,
                add_extra_organizations=add_extra_organizations,
                actor_user=user,
                success_url=success_url,
                cancel_url=cancel_url,
            )
        except Exception as exc:
            return CreateBillingAddonCheckoutSession(
                success=False,
                message=str(exc),
                session=None,
            )

        return CreateBillingAddonCheckoutSession(
            success=True,
            message='Checkout session created.',
            session=BillingCheckoutSessionType(
                checkout_url=checkout_session.checkout_url,
                session_id=checkout_session.session_id,
            ),
        )


class CreateManagedOrganization(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)

    organization = graphene.Field(OrganizationType)
    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @role_required([Roles.ADMIN, Roles.RESOURCE_MANAGER])
    def mutate(root, info, name):
        caller = info.context.user
        if Organization.objects.filter(name=name).exists():
            return CreateManagedOrganization(success=False, message=f"Organization '{name}' already exists.", organization=None)

        if caller.organization and caller.organization.entity_id is None:
            base_name = f"{caller.organization.name} Entity"
            entity_name = base_name
            suffix = 2
            while Entity.objects.filter(name=entity_name).exists():
                entity_name = f"{base_name} ({suffix})"
                suffix += 1
            new_entity = Entity.objects.create(name=entity_name)
            caller.organization.entity = new_entity
            caller.organization.save(update_fields=['entity'])

        billing_profile, _ = OrganizationBillingProfile.objects.get_or_create(
            organization=caller.organization,
            defaults={
                'included_users': OrganizationBillingProfile.BASE_USERS,
                'included_organizations': OrganizationBillingProfile.BASE_ORGANIZATIONS,
            },
        )
        if not billing_profile.has_organization_capacity(1):
            return CreateManagedOrganization(
                success=False,
                message=(
                    f"Organization capacity exceeded. Current quota: {billing_profile.max_organizations} "
                    "managed organizations."
                ),
                organization=None,
            )

        new_org = Organization.objects.create(
            name=name,
            entity=caller.organization.entity,
            max_users=OrganizationBillingProfile.BASE_USERS,
        )
        OrganizationManagerAccess.objects.get_or_create(
            user=caller,
            organization=new_org,
            defaults={'access_role': OrganizationManagerAccess.AccessRole.OWNER, 'created_by': caller},
        )
        OrganizationBillingProfile.objects.get_or_create(
            organization=new_org,
            defaults={
                'included_users': OrganizationBillingProfile.BASE_USERS,
                'included_organizations': OrganizationBillingProfile.BASE_ORGANIZATIONS,
            },
        )

        return CreateManagedOrganization(
            success=True,
            message='Managed organization created successfully.',
            organization=new_org,
        )


class AssignOrganizationManager(graphene.Mutation):
    class Arguments:
        user_id = graphene.ID(required=True)
        organization_id = graphene.UUID(required=True)
        access_role = graphene.String(required=False, default_value='RESOURCE_MANAGER')

    success = graphene.Boolean()
    message = graphene.String()
    access = graphene.Field(OrganizationManagerAccessType)

    @staticmethod
    @role_required([Roles.ADMIN, Roles.RESOURCE_MANAGER])
    def mutate(root, info, user_id, organization_id, access_role='RESOURCE_MANAGER'):
        caller = info.context.user
        if not _caller_can_manage_organization(caller, organization_id):
            raise GraphQLError('Permission denied for this organization.')

        try:
            target_user = CustomUser.objects.get(pk=user_id)
        except CustomUser.DoesNotExist:
            raise GraphQLError('User not found.')

        try:
            target_org = Organization.objects.get(pk=organization_id)
        except Organization.DoesNotExist:
            raise GraphQLError('Organization not found.')

        normalized_role = str(access_role or '').strip().upper()
        if normalized_role not in {
            OrganizationManagerAccess.AccessRole.OWNER,
            OrganizationManagerAccess.AccessRole.RESOURCE_MANAGER,
        }:
            raise GraphQLError('Invalid access role.')

        access, _ = OrganizationManagerAccess.objects.update_or_create(
            user=target_user,
            organization=target_org,
            defaults={
                'access_role': normalized_role,
                'created_by': caller,
            },
        )
        return AssignOrganizationManager(
            success=True,
            message='Manager access granted.',
            access=access,
        )


class Mutation(graphene.ObjectType):
    create_organization = CreateOrganization.Field()
    update_organization = UpdateOrganization.Field()
    delete_organization = DeleteOrganization.Field()
    create_entity = CreateEntity.Field()
    delete_entity = DeleteEntity.Field()
    create_misp_instance = CreateMISPInstance.Field()
    update_misp_instance = UpdateMISPInstance.Field()
    delete_misp_instance = DeleteMISPInstance.Field()
    publish_workbench_open_tide = PublishWorkbenchOpenTide.Field()
    start_opentide_preview_task = StartOpentidePreviewTask.Field()
    set_open_tide_publish_profile = SetOpenTidePublishProfile.Field()
    delete_open_tide_publish_profile = DeleteOpenTidePublishProfile.Field()
    set_platform_credential = SetPlatformCredential.Field()
    delete_platform_credential = DeletePlatformCredential.Field()
    test_platform_connection = TestPlatformConnection.Field()
    upsert_smtp_settings = UpsertSmtpSettings.Field()
    set_shared_smtp_profile = SetSharedSmtpProfile.Field()
    delete_shared_smtp_profile = DeleteSharedSmtpProfile.Field()
    set_organization_smtp_policy = SetOrganizationSmtpPolicy.Field()
    set_organization_shared_flags = SetOrganizationSharedFlags.Field()
    set_org_ai_task_config = SetOrgAiTaskConfig.Field()
    run_org_ai_task_now = RunOrgAiTaskNow.Field()
    create_billing_addon_checkout_session = CreateBillingAddonCheckoutSession.Field()
    create_managed_organization = CreateManagedOrganization.Field()
    assign_organization_manager = AssignOrganizationManager.Field()
    update_dac_deployment_config = UpdateDacDeploymentConfig.Field()
    queue_opentide_hef_import = QueueOpenTideHefImport.Field()
    set_hefaistos_remote_peer = SetHefaistosRemotePeer.Field()
    delete_hefaistos_remote_peer = DeleteHefaistosRemotePeer.Field()
    create_hefaistos_inbound_share_key = CreateHefaistosInboundShareKey.Field()
    revoke_hefaistos_inbound_share_key = RevokeHefaistosInboundShareKey.Field()
    pull_from_remote_hefaistos = PullFromRemoteHefaistos.Field()
