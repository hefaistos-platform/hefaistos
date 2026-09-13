import graphene
import logging
import os
import yaml as pyyaml
from datetime import timedelta
from graphene_django import DjangoObjectType
from django.db import models
from django.db.models import F, Value
from django.db.models.functions import Greatest
from services.publisher import get_publisher
from .models import DetectionRule, RuleRepository, RuleRepositoryRAGFileStatus
from .utils import parse_rule_by_format, detect_rule_format
from .metadata_injector import inject_metadata
from .format_registry import FORMAT_REGISTRY, get_format_spec, normalize_rule_format
from .conversion_service import convert_rule_content
from playbooks.models import DetectionPlaybook, PlaybookGraph
from django.utils import timezone
import json
import requests
from identity.decorators import role_required, Roles
from django.utils.text import slugify
from mgmt_reports.cache_utils import invalidate_mgmt_cave_stats_cache

logger = logging.getLogger(__name__)

QDRANT_COLLECTION_NAME = os.environ.get('QDRANT_TEMPLATE_COLLECTION', 'hefaistos_rule_templates')
QDRANT_BASE_URL = os.environ.get('QDRANT_URL', 'http://qdrant:6333').rstrip('/')
QDRANT_TIMEOUT_SECONDS = float(os.environ.get('QDRANT_TIMEOUT_SECONDS', '8'))


def _qdrant_headers():
    headers = {'Content-Type': 'application/json'}
    api_key = os.environ.get('QDRANT_API_KEY')
    if api_key:
        headers['api-key'] = api_key
    return headers


def _fetch_qdrant_repo_point_count(repository_id: str):
    payload = {
        'exact': False,
        'filter': {
            'must': [
                {
                    'key': 'repository_id',
                    'match': {'value': str(repository_id)},
                }
            ]
        },
    }

    response = requests.post(
        f"{QDRANT_BASE_URL}/collections/{QDRANT_COLLECTION_NAME}/points/count",
        headers=_qdrant_headers(),
        json=payload,
        timeout=QDRANT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    result = (response.json() or {}).get('result') or {}
    return int(result.get('count') or 0)


def _compute_next_scheduled_at(schedule_value: str):
    schedule = (schedule_value or '').upper()
    schedule_hours = {
        '24H': 24,
        '48H': 48,
        '72H': 72,
        'WEEKLY': 168,
    }
    hours = schedule_hours.get(schedule)
    if not hours:
        return None
    return timezone.now() + timedelta(hours=hours)

# --- TYPES ---
# Autocomplete GraphQL types and mutation
class AutocompleteSuggestion(graphene.ObjectType):
    label = graphene.String(required=True)
    kind = graphene.String(required=True)
    insertText = graphene.String(required=True)
    detail = graphene.String()
    documentation = graphene.String()
    sortText = graphene.String()
    filterText = graphene.String()


class AutocompleteResultType(graphene.ObjectType):
    suggestions = graphene.List(AutocompleteSuggestion, required=True)
    isComplete = graphene.Boolean(required=True)


class ValidationIssueType(graphene.ObjectType):
    line = graphene.Int(required=True)
    column = graphene.Int()
    message = graphene.String(required=True)
    severity = graphene.String(required=True)


class ValidationResultType(graphene.ObjectType):
    issues = graphene.List(ValidationIssueType, required=True)


class GetAutocompleteOptions(graphene.Mutation):
    class Arguments:
        format = graphene.String(required=True)
        context = graphene.String(required=True)
        position = graphene.Int(required=True)
        dataSourceId = graphene.ID()

    result = graphene.Field(AutocompleteResultType, required=True)

    @staticmethod
    def mutate(root, info, format, context, position, dataSourceId=None):
        from rules.autocomplete import (
            AQLAutocompleteEngine,
            EQLAutocompleteEngine,
            KQLAutocompleteEngine,
            SPLAutocompleteEngine,
            WazuhAutocompleteEngine,
        )

        fmt = (format or '').upper()
        engine_map = {
            'KQL': KQLAutocompleteEngine,
            'WAZUH': WazuhAutocompleteEngine,
            'SPL': SPLAutocompleteEngine,
            'AQL': AQLAutocompleteEngine,
            'EQL': EQLAutocompleteEngine,
        }
        engine_cls = engine_map.get(fmt)
        if engine_cls is None:
            return GetAutocompleteOptions(result=AutocompleteResultType(suggestions=[], isComplete=True))
        engine = engine_cls()

        try:
            res = engine.get_autocomplete(text=context or '', position=position or 0, data_source_id=dataSourceId)
            suggestions = [
                AutocompleteSuggestion(
                    label=s.label,
                    kind=(getattr(s.kind, 'value', None) or str(s.kind)),
                    insertText=s.insertText,
                    detail=s.detail,
                    documentation=s.documentation,
                    sortText=s.sortText,
                    filterText=s.filterText,
                ) for s in res.suggestions
            ]

            # Telemetry: best-effort event recording (never fails mutation)
            try:
                from .models import AutocompleteEvent
                user = getattr(info.context, 'user', None)
                org = getattr(user, 'organization', None) if user else None
                if org:
                    AutocompleteEvent.objects.create(
                        organization=org,
                        user=user if getattr(user, 'is_authenticated', False) else None,
                        format=fmt,
                        position=position or 0,
                        suggestions_count=len(suggestions),
                        data_source_id=str(dataSourceId) if dataSourceId else None,
                        context_snapshot=(context or '')[:200],
                    )
            except Exception:
                # Silent; analytics should not affect UX
                pass

            return GetAutocompleteOptions(result=AutocompleteResultType(suggestions=suggestions, isComplete=res.isComplete))
        except Exception as e:
            logger.error(f"Autocomplete error: {e}", exc_info=True)
            return GetAutocompleteOptions(result=AutocompleteResultType(suggestions=[], isComplete=True))


class ValidateRuleContent(graphene.Mutation):
    class Arguments:
        format = graphene.String(required=True)
        context = graphene.String(required=True)
        position = graphene.Int(required=True)
        dataSourceId = graphene.ID()

    result = graphene.Field(ValidationResultType, required=True)

    @staticmethod
    def mutate(root, info, format, context, position, dataSourceId=None):
        from rules.autocomplete import (
            AQLAutocompleteEngine,
            EQLAutocompleteEngine,
            KQLAutocompleteEngine,
            SPLAutocompleteEngine,
            WazuhAutocompleteEngine,
        )

        fmt = (format or '').upper()
        engine_map = {
            'KQL': KQLAutocompleteEngine,
            'WAZUH': WazuhAutocompleteEngine,
            'SPL': SPLAutocompleteEngine,
            'AQL': AQLAutocompleteEngine,
            'EQL': EQLAutocompleteEngine,
        }
        engine_cls = engine_map.get(fmt)
        if engine_cls is None:
            return ValidateRuleContent(result=ValidationResultType(issues=[]))
        engine = engine_cls()

        try:
            validator = getattr(engine, 'validate_content', None)
            if callable(validator):
                raw_issues = validator(context or '')
            else:
                is_valid, error = engine.validate_syntax(context or '')
                raw_issues = [] if is_valid else [{
                    'line': 1,
                    'column': 1,
                    'message': error or 'Invalid rule content',
                    'severity': 'error',
                }]

            issues = [
                ValidationIssueType(
                    line=max(1, int(issue.get('line', 1) or 1)),
                    column=int(issue.get('column', 1) or 1) if issue.get('column') is not None else None,
                    message=str(issue.get('message', 'Invalid rule content')),
                    severity=str(issue.get('severity', 'error')),
                )
                for issue in raw_issues
            ]

            return ValidateRuleContent(result=ValidationResultType(issues=issues))
        except Exception as e:
            logger.error(f"Validation error: {e}", exc_info=True)
            return ValidateRuleContent(result=ValidationResultType(issues=[]))

# --- Sigma Rule Conversion Types ---
class ConversionTarget(graphene.ObjectType):
    """Available conversion target backends (e.g., Splunk, Elastic)."""
    name = graphene.String(required=True)
    description = graphene.String()


class ConversionFormat(graphene.ObjectType):
    """Available output formats for a specific backend."""
    name = graphene.String(required=True)
    description = graphene.String()
    target = graphene.String(required=True)


class ConversionPipeline(graphene.ObjectType):
    """Available processing pipelines."""
    name = graphene.String(required=True)
    targets = graphene.List(graphene.String)


class RuleRepositoryType(DjangoObjectType):
    # Explicit computed fields mapped from model properties
    url = graphene.String()
    last_sync = graphene.DateTime()
    token = graphene.String(description="DECRYPTED token. Only accessible by service accounts.")
    rule_count = graphene.Int(description="Number of detection rules currently linked to this repository.")
    # Schedule fields
    auto_pull_enabled = graphene.Boolean()
    auto_pull_schedule = graphene.String()
    next_scheduled_pull = graphene.DateTime()
    provider = graphene.String()
    api_base_url = graphene.String()
    verify_ssl = graphene.Boolean()
    rag_sync_enabled = graphene.Boolean()
    rag_sync_schedule = graphene.String()
    rag_dataset_path = graphene.String()
    rag_branch = graphene.String()
    rag_next_scheduled_sync = graphene.DateTime()
    rag_last_synced = graphene.DateTime()
    rag_last_sync_status = graphene.String()
    rag_last_sync_error = graphene.String()
    rag_last_synced_templates = graphene.Int()
    rag_files = graphene.List(lambda: RuleRepositoryRAGFileType)

    class Meta:
        model = RuleRepository
        # Expose only real model fields here; computed fields are defined above
        fields = (
            "id",
            "organization",
            "name",
            "username",
            "provider",
            "api_base_url",
            "verify_ssl",
            "auto_pull_enabled",
            "auto_pull_schedule",
            "next_scheduled_pull",
            "rag_sync_enabled",
            "rag_sync_schedule",
            "rag_dataset_path",
            "rag_branch",
            "rag_next_scheduled_sync",
            "rag_last_synced",
            "rag_last_sync_status",
            "rag_last_sync_error",
            "rag_last_synced_templates",
        )

    # Resolvers for computed fields
    def resolve_url(self, info):
        # Use git_url directly since 'url' is a property alias
        return self.git_url

    def resolve_last_sync(self, info):
        return self.last_synced

    def resolve_token(self, info):
        user = info.context.user
        # Allow service accounts: connector_svc, or usernames containing 'service'
        if user and getattr(user, 'username', ''):
            username = user.username.lower()
            if username == 'connector_svc' or 'service' in username:
                return getattr(self, 'token', None)
        return None

    def resolve_rule_count(self, info):
        try:
            return DetectionRule.objects.filter(repository_id=self.id).count()
        except Exception:
            return 0

    def resolve_auto_pull_enabled(self, info):
        return getattr(self, 'auto_pull_enabled', False)

    def resolve_auto_pull_schedule(self, info):
        return getattr(self, 'auto_pull_schedule', 'DISABLED')

    def resolve_next_scheduled_pull(self, info):
        return getattr(self, 'next_scheduled_pull', None)

    def resolve_rag_sync_enabled(self, info):
        return getattr(self, 'rag_sync_enabled', False)

    def resolve_rag_sync_schedule(self, info):
        return getattr(self, 'rag_sync_schedule', 'DISABLED')

    def resolve_rag_dataset_path(self, info):
        return getattr(self, 'rag_dataset_path', '')

    def resolve_rag_branch(self, info):
        return getattr(self, 'rag_branch', 'main')

    def resolve_rag_next_scheduled_sync(self, info):
        return getattr(self, 'rag_next_scheduled_sync', None)

    def resolve_rag_last_synced(self, info):
        return getattr(self, 'rag_last_synced', None)

    def resolve_rag_last_sync_status(self, info):
        return getattr(self, 'rag_last_sync_status', 'IDLE')

    def resolve_rag_last_sync_error(self, info):
        return getattr(self, 'rag_last_sync_error', '')

    def resolve_rag_last_synced_templates(self, info):
        return getattr(self, 'rag_last_synced_templates', 0)

    def resolve_rag_files(self, info):
        try:
            return self.rag_files.all().order_by('source_path')
        except Exception:
            return []


class RuleRepositoryRAGFileType(DjangoObjectType):
    class Meta:
        model = RuleRepositoryRAGFileStatus
        fields = (
            'id',
            'source_path',
            'source_branch',
            'language',
            'ingestion_status',
            'templates_count',
            'last_synced_at',
            'last_error',
            'used_in_generation',
            'usage_count',
            'last_used_at',
            'created_at',
            'updated_at',
        )

class RuleType(DjangoObjectType):
    tags = graphene.List(graphene.String)
    class Meta:
        model = DetectionRule
        fields = "__all__"

    def resolve_tags(self, info):
        try:
            if self.playbook:
                return list(self.playbook.tags.names())
        except Exception:
            return []
        return []

# --- QUERIES ---

# --- CONNECTION TYPES (module-level to avoid NameError in class scopes) ---
class RuleEdge(graphene.ObjectType):
    cursor = graphene.String()
    node = graphene.Field(lambda: RuleType)

class PageInfo(graphene.ObjectType):
    has_next_page = graphene.Boolean()
    end_cursor = graphene.String()

class RulesConnection(graphene.ObjectType):
    edges = graphene.List(RuleEdge)
    page_info = graphene.Field(PageInfo)
    total_count = graphene.Int()


# --- STATISTICS TYPES ---
class TechniqueStat(graphene.ObjectType):
    technique_id = graphene.String()
    count = graphene.Int()

class TimeBucket(graphene.ObjectType):
    date = graphene.String()
    count = graphene.Int()

class RepoStat(graphene.ObjectType):
    id = graphene.ID()
    name = graphene.String()
    rule_count = graphene.Int()
    last_sync = graphene.DateTime()
    stale = graphene.Boolean()

class TagStat(graphene.ObjectType):
    tag = graphene.String()
    count = graphene.Int()

class TagPairStat(graphene.ObjectType):
    tag_a = graphene.String()
    tag_b = graphene.String()
    count = graphene.Int()

class AuthorStat(graphene.ObjectType):
    name = graphene.String()
    count = graphene.Int()
    last_activity = graphene.DateTime()

class ChangeItem(graphene.ObjectType):
    id = graphene.ID()
    title = graphene.String()
    status = graphene.String()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()
    change_type = graphene.String()
class RuleStatistics(graphene.ObjectType):
    total = graphene.Int()
    created_last_24h = graphene.Int()
    created_last_7d = graphene.Int()
    created_last_30d = graphene.Int()
    unchanged_90d_plus = graphene.Int()
    active_count = graphene.Int()
    deprecated_count = graphene.Int()
    avg_techniques_per_rule = graphene.Float()
    with_playbooks_count = graphene.Int()
    standalone_count = graphene.Int()
    top_techniques = graphene.List(TechniqueStat)
    top_subtechniques = graphene.List(TechniqueStat)
    created_series = graphene.List(TimeBucket, description="Counts per day for the last N days")
    updated_series = graphene.List(TimeBucket, description="Updated counts per day for the last N days")
    repositories = graphene.List(RepoStat)
    top_tags = graphene.List(TagStat)
    tag_cooccurrence = graphene.List(TagPairStat)
    top_authors = graphene.List(AuthorStat)
    inactive_authors = graphene.List(AuthorStat)
    recent_changes = graphene.List(ChangeItem)


class RuleRepositoryRagHealth(graphene.ObjectType):
    repository_id = graphene.ID()
    repository_name = graphene.String()
    rag_sync_enabled = graphene.Boolean()
    rag_last_sync_status = graphene.String()
    rag_last_synced = graphene.DateTime()
    rag_last_synced_templates = graphene.Int()
    ingested_files = graphene.Int()
    failed_files = graphene.Int()
    qdrant_point_count = graphene.Int()
    qdrant_status = graphene.String()
    qdrant_error = graphene.String()


class Query(graphene.ObjectType):
    rule = graphene.Field(RuleType, id=graphene.ID(required=True))
    search_rules = graphene.List(
        RuleType,
        search=graphene.String(),
        limit=graphene.Int(),
        offset=graphene.Int()
    )

    # New: Relay-style connection with rich filters and pagination
    rules_connection = graphene.Field(
        RulesConnection,
        text=graphene.String(),
        status=graphene.List(graphene.String),
        repository_id=graphene.ID(),
        author=graphene.String(),
        playbook_id=graphene.UUID(),
        has_playbook=graphene.Boolean(),
        tags=graphene.List(graphene.String),
        technique_id=graphene.String(),
        sort=graphene.String(),
        first=graphene.Int(required=True),
        after=graphene.String()
    )

    # --- NEW QUERY ---
    all_rule_repositories = graphene.List(RuleRepositoryType)
    # Single repository by ID (org scoped)
    rule_repository = graphene.Field(RuleRepositoryType, id=graphene.ID(required=True))

    # Fetch the rule linked to a specific playbook graph
    detection_rule_by_playbook = graphene.Field(RuleType, playbook_id=graphene.UUID(required=True))

    # Search all rules for autocomplete (used by rule picker in manual editor)
    search_all_rules = graphene.List(
        RuleType,
        query=graphene.String(required=True),
        format=graphene.String(description="Filter by format: KQL, EQL, WAZUH, SPL, AQL, OTHER"),
        limit=graphene.Int(default_value=15),
        description="Search rules by title for autocomplete in rule picker."
    )

    # Rule statistics for dashboard panels
    rule_statistics = graphene.Field(
        RuleStatistics,
        top_n=graphene.Int(default_value=10),
        series_days=graphene.Int(default_value=30),
    )

    rule_repository_rag_health = graphene.List(
        RuleRepositoryRagHealth,
        description="Per-repository RAG sync health and Qdrant template counts.",
    )

    def resolve_rule(self, info, id):
        # Security: Not implemented, but should be org-scoped
        return DetectionRule.objects.get(pk=id, organization=info.context.user.organization)

    def resolve_search_rules(self, info, search=None, limit=None, offset=None):
        # Security: Already org-scoped
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        queryset = DetectionRule.objects.filter(organization=user.organization)
        if search:
            queryset = queryset.filter(title__icontains=search)
        # Apply basic pagination if provided
        if offset is not None and offset < 0:
            offset = 0
        if limit is not None:
            limit = max(1, min(limit, 200))  # safety cap
        if offset is not None and limit is not None:
            return queryset[offset: offset + limit]
        if limit is not None:
            return queryset[:limit]
        return queryset

    def resolve_rules_connection(self, info, **args):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        # Base queryset scoped to org
        qs = DetectionRule.objects.filter(organization=user.organization)

        # Filters
        text = args.get('text')
        if text:
            # Try similarity-based ranking (requires pg_trgm extension)
            try:
                # Annotate similarity scores per field and compute the greatest
                qs_sim = qs.annotate(
                    sim_title=models.Func(F('title'), Value(text), function='SIMILARITY'),
                    sim_desc=models.Func(F('description'), Value(text), function='SIMILARITY'),
                    sim_raw=models.Func(F('raw_content'), Value(text), function='SIMILARITY'),
                ).annotate(sim=Greatest(F('sim_title'), F('sim_desc'), F('sim_raw')))
                # Prefer results above a lower threshold, but don't exclude entirely if tiny result set
                qs_primary = qs_sim.filter(sim__gt=0.1)
                if qs_primary.count() < 5:
                    # Broaden with icontains union for short queries or sparse matches
                    qs_fallback = qs.filter(
                        models.Q(title__icontains=text) |
                        models.Q(description__icontains=text) |
                        models.Q(raw_content__icontains=text)
                    )
                    qs = (qs_primary | qs_fallback).order_by('-sim')
                else:
                    qs = qs_primary.order_by('-sim')
            except Exception:
                # Fallback to simple icontains if SIMILARITY function is unavailable
                qs = qs.filter(
                    models.Q(title__icontains=text) |
                    models.Q(description__icontains=text) |
                    models.Q(raw_content__icontains=text)
                )

        statuses = args.get('status') or []
        if statuses:
            qs = qs.filter(status__in=statuses)

        repo_id = args.get('repository_id')
        if repo_id:
            qs = qs.filter(repository__id=repo_id)

        author = args.get('author')
        if author:
            qs = qs.filter(author__icontains=author)

        playbook_id = args.get('playbook_id')
        if playbook_id:
            qs = qs.filter(playbook__id=playbook_id)

        has_playbook = args.get('has_playbook')
        if has_playbook is True:
            qs = qs.filter(playbook__isnull=False)
        elif has_playbook is False:
            qs = qs.filter(playbook__isnull=True)

        # Tags filter: match any provided tag assigned to the linked PlaybookGraph
        # Broaden to exact (iexact) OR partial (icontains) and also try slug icontains
        tags = args.get('tags') or []
        if tags:
            tag_q = models.Q()
            for raw in tags:
                if not raw:
                    continue
                t = str(raw).strip()
                s = slugify(t)
                tag_q |= (
                    models.Q(playbook__tags__name__iexact=t) |
                    models.Q(playbook__tags__name__icontains=t) |
                    models.Q(playbook__tags__slug__icontains=s)
                )
            if tag_q:
                qs = qs.filter(tag_q).distinct()

        # Technique filter (heuristic: search technique ID within raw_content/title/description)
        technique = args.get('technique_id')
        if technique:
            qs = qs.filter(
                models.Q(title__icontains=technique) |
                models.Q(description__icontains=technique) |
                models.Q(raw_content__icontains=technique)
            )

        # Sorting
        sort = (args.get('sort') or '').upper()
        order_map = {
            'TITLE_ASC': 'title',
            'TITLE_DESC': '-title',
            'UPDATED_DESC': '-updated_at',
            'UPDATED_ASC': 'updated_at',
            'CREATED_DESC': '-created_at',
            'CREATED_ASC': 'created_at',
        }
        qs = qs.order_by(order_map.get(sort, '-id'))

        total = qs.count()

        # Cursor-based pagination using opaque base64 cursor of integer offset
        first = max(1, min(args.get('first') or 25, 100))
        after = args.get('after')
        start = 0
        if after:
            try:
                import base64
                start = int(base64.b64decode(after).decode('utf-8'))
            except Exception:
                start = 0

        slice_qs = qs[start:start+first]
        edges = []
        for idx, item in enumerate(slice_qs):
            cursor_val = start + idx + 1
            import base64
            cursor = base64.b64encode(str(cursor_val).encode('utf-8')).decode('utf-8')
            edges.append(RuleEdge(cursor=cursor, node=item))

        end_cursor = edges[-1].cursor if edges else after
        has_next_page = (start + first) < total

        return RulesConnection(
            edges=edges,
            page_info=PageInfo(has_next_page=has_next_page, end_cursor=end_cursor),
            total_count=total
        )
    # --- NEW RESOLVER ---
    def resolve_all_rule_repositories(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        return RuleRepository.objects.filter(organization=user.organization)

    def resolve_rule_repository(self, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        # Service accounts (connector_svc) can access any repository
        # to support cross-org operations like scheduled pulls
        is_service_account = (
            hasattr(user, 'username') and
            (user.username == 'connector_svc' or 'service' in user.username.lower())
        )

        try:
            if is_service_account:
                return RuleRepository.objects.get(pk=id)
            else:
                return RuleRepository.objects.get(pk=id, organization=user.organization)
        except RuleRepository.DoesNotExist:
            return None

    def resolve_detection_rule_by_playbook(self, info, playbook_id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")
        return DetectionRule.objects.filter(playbook__id=playbook_id, organization=user.organization).first()

    def resolve_search_all_rules(self, info, query, format=None, limit=15):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        from django.db.models import Q

        qs = DetectionRule.objects.filter(organization=user.organization)

        # Filter by format if specified
        if format:
            qs = qs.filter(format=format.upper())

        # Search by title or description (case-insensitive)
        qs = qs.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )

        # Order by title and limit
        return qs.order_by('title')[:limit]

    def resolve_rule_statistics(self, info, top_n=10, series_days=30):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        qs = DetectionRule.objects.filter(organization=user.organization)
        now = timezone.now()

        # Time windows
        from datetime import timedelta
        last_24h = now - timedelta(days=1)
        last_7d = now - timedelta(days=7)
        last_30d = now - timedelta(days=30)
        last_90d = now - timedelta(days=90)

        total = qs.count()
        created_24h = qs.filter(created_at__gte=last_24h).count()
        created_7d = qs.filter(created_at__gte=last_7d).count()
        created_30d = qs.filter(created_at__gte=last_30d).count()
        unchanged_90 = qs.filter(updated_at__lte=last_90d).count()

        # Status metrics
        active_count = qs.filter(status__iexact='active').count()
        deprecated_count = qs.filter(status__iexact='deprecated').count()

        # Playbook linkage
        with_playbooks_count = qs.filter(playbook__isnull=False).count()
        standalone_count = qs.filter(playbook__isnull=True).count()

        # Technique extraction via regex on raw_content/title/description
        import re
        tech_regex = re.compile(r"T\d{4}(?:\.\d{3})?")
        tech_counts = {}
        subtech_counts = {}
        total_techniques = 0
        rules_with_techniques = 0
        for rule in qs.only('title', 'description', 'raw_content'):
            text = (rule.title or '') + '\n' + (rule.description or '') + '\n' + (rule.raw_content or '')
            rule_top_techniques = set()
            rule_subtechniques = set()
            for match in tech_regex.findall(text):
                if '.' in match:
                    rule_subtechniques.add(match)
                    # Derive parent technique ID (e.g. T1218 from T1218.005)
                    rule_top_techniques.add(match[:5])
                else:
                    rule_top_techniques.add(match)
            # Increment per-rule counts (each technique counted once per rule)
            for tech in rule_top_techniques:
                tech_counts[tech] = tech_counts.get(tech, 0) + 1
            for subtech in rule_subtechniques:
                subtech_counts[subtech] = subtech_counts.get(subtech, 0) + 1
            all_unique = rule_top_techniques | rule_subtechniques
            if all_unique:
                total_techniques += len(all_unique)
                rules_with_techniques += 1

        # Calculate average techniques per rule
        avg_techniques = round(total_techniques / total, 2) if total > 0 else 0.0

        # Top-N lists
        def top_list(counts):
            items = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:max(1, top_n)]
            return [TechniqueStat(technique_id=k, count=v) for k, v in items]

        # Build created/updated series buckets (last N days)
        created_series = []
        updated_series = []
        try:
            days = max(1, min(series_days, 120))
        except Exception:
            days = 30
        for i in range(days-1, -1, -1):
            day = (now - timedelta(days=i)).date()
            c = qs.filter(created_at__date=day).count()
            created_series.append(TimeBucket(date=str(day), count=c))
            u = qs.filter(updated_at__date=day).count()
            updated_series.append(TimeBucket(date=str(day), count=u))

        # Repository health
        repos_stats = []
        try:
            repos = RuleRepository.objects.filter(organization=user.organization)
            stale_threshold = now - timedelta(days=7)
            for r in repos:
                count = DetectionRule.objects.filter(organization=user.organization, repository_id=r.id).count()
                last_sync = getattr(r, 'last_synced', None)
                stale = bool(last_sync and last_sync < stale_threshold)
                repos_stats.append(RepoStat(id=str(r.id), name=r.name, rule_count=count, last_sync=last_sync, stale=stale))
        except Exception:
            repos_stats = []

        # Tag analytics: top tags and co-occurrence
        tag_counts = {}
        co_counts = {}
        for rule in qs.select_related('playbook').only('playbook'):
            tags = []
            try:
                if rule.playbook:
                    tags = list(rule.playbook.tags.names())
            except Exception:
                tags = []
            # Count tags
            for t in tags:
                tag_counts[t] = tag_counts.get(t, 0) + 1
            # Count co-occurrence pairs
            for i in range(len(tags)):
                for j in range(i+1, len(tags)):
                    a, b = sorted([tags[i], tags[j]])
                    key = (a, b)
                    co_counts[key] = co_counts.get(key, 0) + 1

        top_tags = sorted(tag_counts.items(), key=lambda kv: kv[1], reverse=True)[:max(1, top_n)]
        tag_co = sorted(co_counts.items(), key=lambda kv: kv[1], reverse=True)[:20]

        # Authors & Activity
        author_counts = {}
        author_last = {}
        for rule in qs.only('author', 'created_at', 'updated_at'):
            name = (rule.author or '').strip() or 'Unknown'
            author_counts[name] = author_counts.get(name, 0) + 1
            last = max(rule.updated_at or rule.created_at, rule.created_at)
            prev = author_last.get(name)
            author_last[name] = last if (prev is None or (last and prev and last > prev)) else prev
        top_authors = sorted(author_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
        inactive_authors = []
        inactive_threshold = now - timedelta(days=30)
        for name, last in author_last.items():
            if last and last < inactive_threshold:
                inactive_authors.append((name, author_counts.get(name, 0), last))
        inactive_authors = sorted(inactive_authors, key=lambda x: x[2])[:10]

        # Recent changes (last 50 by updated_at)
        recent = qs.order_by('-updated_at')[:50]
        changes = []
        for r in recent:
            change_type = 'UPDATED'
            try:
                if r.status and r.status.lower() == 'deprecated':
                    change_type = 'DEPRECATED'
                elif r.created_at and (r.updated_at is None or r.updated_at <= r.created_at):
                    change_type = 'CREATED'
            except Exception:
                pass
            changes.append(ChangeItem(id=str(r.id), title=r.title, status=r.status or '', created_at=r.created_at, updated_at=r.updated_at, change_type=change_type))

        return RuleStatistics(
            total=total,
            created_last_24h=created_24h,
            created_last_7d=created_7d,
            created_last_30d=created_30d,
            unchanged_90d_plus=unchanged_90,
            active_count=active_count,
            deprecated_count=deprecated_count,
            avg_techniques_per_rule=avg_techniques,
            with_playbooks_count=with_playbooks_count,
            standalone_count=standalone_count,
            top_techniques=top_list(tech_counts),
            top_subtechniques=top_list(subtech_counts),
            created_series=created_series,
            updated_series=updated_series,
            repositories=repos_stats,
            top_tags=[TagStat(tag=k, count=v) for k, v in top_tags],
            tag_cooccurrence=[TagPairStat(tag_a=a, tag_b=b, count=v) for (a, b), v in tag_co],
            top_authors=[AuthorStat(name=name, count=count, last_activity=author_last.get(name)) for name, count in top_authors],
            inactive_authors=[AuthorStat(name=name, count=count, last_activity=last) for (name, count, last) in inactive_authors],
            recent_changes=changes,
        )

    def resolve_rule_repository_rag_health(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        repositories = RuleRepository.objects.filter(organization=user.organization).order_by('name')
        items = []

        for repo in repositories:
            rag_files_qs = repo.rag_files.all()
            ingested_files = rag_files_qs.filter(
                ingestion_status=RuleRepositoryRAGFileStatus.IngestionStatus.INGESTED
            ).count()
            failed_files = rag_files_qs.filter(
                ingestion_status=RuleRepositoryRAGFileStatus.IngestionStatus.FAILED
            ).count()

            qdrant_point_count = 0
            qdrant_status = 'DISABLED' if not repo.rag_sync_enabled else 'OK'
            qdrant_error = ''

            if repo.rag_sync_enabled:
                try:
                    qdrant_point_count = _fetch_qdrant_repo_point_count(str(repo.id))
                except Exception as exc:
                    qdrant_status = 'ERROR'
                    qdrant_error = str(exc)

            items.append(
                RuleRepositoryRagHealth(
                    repository_id=str(repo.id),
                    repository_name=repo.name,
                    rag_sync_enabled=bool(repo.rag_sync_enabled),
                    rag_last_sync_status=repo.rag_last_sync_status,
                    rag_last_synced=repo.rag_last_synced,
                    rag_last_synced_templates=repo.rag_last_synced_templates,
                    ingested_files=ingested_files,
                    failed_files=failed_files,
                    qdrant_point_count=qdrant_point_count,
                    qdrant_status=qdrant_status,
                    qdrant_error=qdrant_error,
                )
            )

        return items


# --- MUTATIONS ---

class CreateRuleRepository(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        url = graphene.String(required=True)
        username = graphene.String(required=False)
        token = graphene.String(required=False, description="The access token. Will be encrypted.")
        provider = graphene.String(required=False, description="AUTO, GITHUB, GITLAB, or GITEA")
        api_base_url = graphene.String(required=False, description="Optional custom API base URL for self-hosted providers.")
        verify_ssl = graphene.Boolean(required=False, default_value=True, description="Verify TLS certificates for repository API calls.")
        rag_sync_enabled = graphene.Boolean(required=False, description="Enable/disable RAG template sync for this repository")
        rag_sync_schedule = graphene.String(required=False, description="RAG sync schedule: DISABLED, 24H, 48H, 72H, WEEKLY")
        rag_dataset_path = graphene.String(required=False, description="Repository dataset path/glob for JSONL/KQL/EQL/SPL/WAZUH template sources")
        rag_branch = graphene.String(required=False, description="Branch to use for RAG sync")

    repository = graphene.Field(RuleRepositoryType)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(
        root,
        info,
        name,
        url,
        username=None,
        token=None,
        provider='AUTO',
        api_base_url=None,
        verify_ssl=True,
        rag_sync_enabled=False,
        rag_sync_schedule='DISABLED',
        rag_dataset_path='',
        rag_branch='main',
    ):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        rag_schedule_value = (rag_sync_schedule or 'DISABLED').upper()
        valid_rag_schedules = {'DISABLED', '24H', '48H', '72H', 'WEEKLY'}
        if rag_schedule_value not in valid_rag_schedules:
            rag_schedule_value = 'DISABLED'

        rag_enabled = bool(rag_sync_enabled)
        rag_next_sync = (
            _compute_next_scheduled_at(rag_schedule_value)
            if rag_enabled and rag_schedule_value != 'DISABLED'
            else None
        )

        # Map GraphQL 'url' argument to model field 'git_url'
        repo = RuleRepository(
            name=name,
            git_url=url,
            username=username,
            provider=(provider or 'AUTO').upper(),
            api_base_url=api_base_url or None,
            verify_ssl=bool(verify_ssl),
            rag_sync_enabled=rag_enabled,
            rag_sync_schedule=rag_schedule_value,
            rag_dataset_path=(rag_dataset_path or '').strip(),
            rag_branch=(rag_branch or 'main').strip() or 'main',
            rag_next_scheduled_sync=rag_next_sync,
            organization=user.organization
        )
        if token:
            repo.token = token # Use the setter to encrypt
        repo.save()
        # Publish repository.created event for admin notifications
        try:
            publisher = get_publisher()
            publisher.publish_message('repository.created', {
                'repository_id': str(repo.id),
                'name': repo.name,
                'organization_id': str(user.organization.id),
                'actor_id': str(user.id),
            })
        except Exception:
            pass
        return CreateRuleRepository(repository=repo)

class UpdateRuleRepository(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        name = graphene.String()
        url = graphene.String()
        username = graphene.String()
        token = graphene.String(description="A new token. If left blank, the old token is preserved.")
        provider = graphene.String(description="AUTO, GITHUB, GITLAB, or GITEA")
        api_base_url = graphene.String(description="Optional custom API base URL for self-hosted providers.")
        verify_ssl = graphene.Boolean(description="Verify TLS certificates for repository API calls.")
        # Schedule fields
        auto_pull_enabled = graphene.Boolean(description="Enable/disable automatic pulls")
        auto_pull_schedule = graphene.String(description="Pull schedule: DISABLED, 24H, 48H, 72H, WEEKLY")
        # RAG sync fields
        rag_sync_enabled = graphene.Boolean(description="Enable/disable automatic RAG template sync")
        rag_sync_schedule = graphene.String(description="RAG sync schedule: DISABLED, 24H, 48H, 72H, WEEKLY")
        rag_dataset_path = graphene.String(description="Repository dataset path/glob for JSONL/KQL/EQL/SPL/WAZUH RAG sources")
        rag_branch = graphene.String(description="Branch used for RAG sync")

    repository = graphene.Field(RuleRepositoryType)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, id, **kwargs):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        try:
            repo = RuleRepository.objects.get(pk=id, organization=user.organization)
        except RuleRepository.DoesNotExist:
            raise Exception("Repository not found")

        # Handle token separately (encrypt if provided and non-empty)
        if 'token' in kwargs:
            token_value = kwargs.pop('token')
            if token_value:
                repo.token = token_value

        # Map GraphQL 'url' to model 'git_url'
        if 'url' in kwargs:
            repo.git_url = kwargs.pop('url')

        if 'provider' in kwargs:
            provider_value = (kwargs.pop('provider') or 'AUTO').upper()
            valid = {'AUTO', 'GITHUB', 'GITLAB', 'GITEA'}
            if provider_value not in valid:
                raise Exception(f"Invalid provider '{provider_value}'. Valid values: {', '.join(sorted(valid))}")
            repo.provider = provider_value

        if 'api_base_url' in kwargs:
            repo.api_base_url = kwargs.pop('api_base_url') or None

        # Handle schedule updates
        schedule_changed = False
        if 'auto_pull_enabled' in kwargs:
            repo.auto_pull_enabled = kwargs.pop('auto_pull_enabled')
            schedule_changed = True

        if 'auto_pull_schedule' in kwargs:
            schedule = kwargs.pop('auto_pull_schedule')
            valid_schedules = ['DISABLED', '24H', '48H', '72H', 'WEEKLY']
            if schedule and schedule.upper() in valid_schedules:
                repo.auto_pull_schedule = schedule.upper()
                schedule_changed = True

        # Calculate next scheduled pull if schedule changed and enabled
        if schedule_changed and repo.auto_pull_enabled and repo.auto_pull_schedule != 'DISABLED':
            repo.next_scheduled_pull = _compute_next_scheduled_at(repo.auto_pull_schedule)
        elif not repo.auto_pull_enabled or repo.auto_pull_schedule == 'DISABLED':
            repo.next_scheduled_pull = None

        # Handle RAG sync schedule updates
        rag_schedule_changed = False
        if 'rag_sync_enabled' in kwargs:
            repo.rag_sync_enabled = bool(kwargs.pop('rag_sync_enabled'))
            rag_schedule_changed = True

        if 'rag_sync_schedule' in kwargs:
            rag_schedule = (kwargs.pop('rag_sync_schedule') or '').upper()
            valid_rag_schedules = ['DISABLED', '24H', '48H', '72H', 'WEEKLY']
            if rag_schedule in valid_rag_schedules:
                repo.rag_sync_schedule = rag_schedule
                rag_schedule_changed = True

        if 'rag_dataset_path' in kwargs:
            repo.rag_dataset_path = (kwargs.pop('rag_dataset_path') or '').strip()

        if 'rag_branch' in kwargs:
            repo.rag_branch = (kwargs.pop('rag_branch') or 'main').strip() or 'main'

        if rag_schedule_changed and repo.rag_sync_enabled and repo.rag_sync_schedule != 'DISABLED':
            repo.rag_next_scheduled_sync = _compute_next_scheduled_at(repo.rag_sync_schedule)
        elif not repo.rag_sync_enabled or repo.rag_sync_schedule == 'DISABLED':
            repo.rag_next_scheduled_sync = None

        # Update remaining simple fields present on the model
        for field, value in kwargs.items():
            if value is not None:
                setattr(repo, field, value)

        repo.save()
        return UpdateRuleRepository(repository=repo)

class DeleteRuleRepository(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    ok = graphene.Boolean()

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        try:
            repo = RuleRepository.objects.get(pk=id, organization=user.organization)
        except RuleRepository.DoesNotExist:
            raise Exception("Repository not found")

        repo.delete()
        return DeleteRuleRepository(ok=True)

class PullRuleRepository(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    ok = graphene.Boolean()
    repository = graphene.Field(RuleRepositoryType)
    message = graphene.String()

    class Meta:
        description = "Publishes an event to RabbitMQ to pull a rule repository."

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        try:
            repo = RuleRepository.objects.get(pk=id, organization=user.organization)
        except RuleRepository.DoesNotExist:
            raise Exception("Repository not found")

        publisher = get_publisher()
        routing_key = "rule.repo.pull.requested"
        message_body = {
            "action": "pull_repo",
            "repository_id": str(repo.id),
            "organization_id": str(user.organization.id),
            "triggered_by_user_id": str(user.id)
        }

        try:
            publisher.publish_message(routing_key, message_body)
        except Exception as e:
            logger.error(f"Failed to queue pull request for repository {id}: {e}")
            return PullRuleRepository(
                ok=False,
                repository=repo,
                message=f"Failed to queue pull request: {str(e)}"
            )

        # Return current repository data so UI can update immediately
        return PullRuleRepository(ok=True, repository=repo, message="Pull request queued successfully")


class SyncRuleRepositoryRag(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    ok = graphene.Boolean()
    repository = graphene.Field(RuleRepositoryType)
    message = graphene.String()

    class Meta:
        description = "Publishes an event to RabbitMQ to sync repository RAG templates into Qdrant."

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        try:
            repo = RuleRepository.objects.get(pk=id, organization=user.organization)
        except RuleRepository.DoesNotExist:
            raise Exception("Repository not found")

        publisher = get_publisher()
        routing_key = "rule.repo.rag.sync.requested"
        message_body = {
            "action": "sync_rag_repo",
            "repository_id": str(repo.id),
            "organization_id": str(user.organization.id),
            "triggered_by_user_id": str(user.id),
        }

        status_updated_at = timezone.now()
        repo.rag_last_sync_status = RuleRepository.RAGSyncStatus.QUEUED
        repo.rag_last_sync_status_at = status_updated_at
        repo.rag_last_sync_error = ''
        repo.save(update_fields=['rag_last_sync_status', 'rag_last_sync_status_at', 'rag_last_sync_error'])

        try:
            publisher.publish_message(routing_key, message_body)
        except Exception as e:
            logger.error(f"Failed to queue RAG sync request for repository {id}: {e}")
            repo.rag_last_sync_status = RuleRepository.RAGSyncStatus.FAILED
            repo.rag_last_sync_status_at = timezone.now()
            repo.rag_last_sync_error = str(e)
            repo.save(update_fields=['rag_last_sync_status', 'rag_last_sync_status_at', 'rag_last_sync_error'])
            return SyncRuleRepositoryRag(
                ok=False,
                repository=repo,
                message=f"Failed to queue RAG sync request: {str(e)}",
            )

        return SyncRuleRepositoryRag(ok=True, repository=repo, message="RAG sync request queued successfully")


class SaveDetectionRule(graphene.Mutation):
    class Arguments:
        playbook_id = graphene.UUID(required=True)
        raw_yaml = graphene.String(required=True, description="Rule content (KQL, EQL, Wazuh XML, Splunk SPL, or AQL)")
        format = graphene.String(required=False, description="KQL (default), EQL, WAZUH, SPL, AQL, or OTHER")
        title = graphene.String(required=False, description="Optional rule title used for file naming and persistence")
        description = graphene.String(required=False, description="Optional rule description for metadata header")
        author = graphene.String(required=False, description="Optional rule author for metadata header")
        tags = graphene.List(graphene.String, required=False, description="Optional tags for metadata header")
        auto_commit = graphene.Boolean(required=False, default_value=False, description="Commit OPENTIDE rule to Git repository after saving")
        commit_message = graphene.String(required=False, description="Custom Git commit message (optional)")

    success = graphene.Boolean()
    message = graphene.String()
    rule = graphene.Field(RuleType)
    commit_sha = graphene.String(description="Git commit SHA after successful auto-commit")
    errors = graphene.List(graphene.String, description="Validation or Git errors")
    filename = graphene.String(description="Suggested saved filename using title + native extension")

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, playbook_id, raw_yaml, format=None, title=None, description=None, author=None, tags=None, auto_commit=False, commit_message=None):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        # 1) Load the graph and validate org ownership
        try:
            graph = PlaybookGraph.objects.get(pk=playbook_id, organization=user.organization)
        except PlaybookGraph.DoesNotExist:
            raise Exception("Playbook not found or you do not have permission")

        # 2) Parse into model fields based on format
        # Determine format: prefer explicit arg, but auto-correct if content suggests otherwise
        fmt_arg = normalize_rule_format(format)
        detected = detect_rule_format(raw_yaml)
        fmt = fmt_arg if fmt_arg in ('KQL', 'EQL', 'WAZUH', 'SPL', 'AQL', 'OTHER', 'OPENTIDE') else detected
        # Auto-detect OpenTide format by checking YAML structure (must have both 'metadata' and
        # 'platforms' as top-level dict keys) rather than string matching, to avoid false positives.
        if fmt != 'OPENTIDE':
            try:
                _parsed = pyyaml.safe_load(raw_yaml)
                if (isinstance(_parsed, dict)
                        and isinstance(_parsed.get('metadata'), dict)
                        and isinstance(_parsed.get('platforms'), dict)):
                    fmt = 'OPENTIDE'
            except Exception:
                pass
        validated_rule = None
        try:
            author_name = getattr(user, 'username', '')
            if fmt == 'OPENTIDE':
                try:
                    rule_data = pyyaml.safe_load(raw_yaml) or {}
                except Exception:
                    rule_data = {}

                # Pydantic validation for OPENTIDE rules
                from pydantic import ValidationError as PydanticValidationError
                from .opentide_schemas import OpenTideRule as OpenTideRuleValidator
                try:
                    validated_rule = OpenTideRuleValidator(**rule_data)
                except PydanticValidationError as e:
                    validation_errors = []
                    for error in e.errors():
                        field_path = ' -> '.join(str(loc) for loc in error['loc'])
                        validation_errors.append(f"{field_path}: {error['msg']}")
                    return SaveDetectionRule(
                        success=False,
                        message="OpenTide schema validation failed",
                        rule=None,
                        commit_sha=None,
                        errors=validation_errors,
                    )

                metadata = rule_data.get('metadata', {})
                extracted = {
                    'title': metadata.get('title', graph.title),
                    'description': metadata.get('description', ''),
                    'author': metadata.get('author', author_name),
                    'status': metadata.get('response', {}).get('test_status', 'experimental') if isinstance(metadata.get('response'), dict) else 'experimental',
                }
            else:
                extracted = parse_rule_by_format(raw_yaml, fmt, fallback_author=author_name)
        except ValueError as e:
            return SaveDetectionRule(success=False, message=str(e), errors=[str(e)])

        # 3) Determine repository: prefer org-scoped repo named "Rule Repo"
        repo = RuleRepository.objects.filter(
            organization=user.organization,
            name="Rule Repo"
        ).first()
        if repo is None:
            # Create a lightweight placeholder if it doesn't exist yet
            repo = RuleRepository.objects.create(
                organization=user.organization,
                name="Rule Repo",
                git_url=None,
            )

        # 4) Upsert rule linked to this graph
        fmt_norm = fmt if fmt in ('KQL', 'EQL', 'WAZUH', 'SPL', 'AQL', 'OTHER', 'OPENTIDE') else 'OTHER'

        # Rule title uses the format: "{playbook title}-{format}" (e.g. "mshta-spl")
        extracted_title = (title or '').strip()
        extracted['title'] = extracted_title or f"{graph.title}-{fmt_norm.lower()}"
        if description is not None:
            extracted['description'] = description
        if author is not None:
            extracted['author'] = author

        # Create/update the rule first (with original content) to obtain the DB sigma_id
        defaults = {
            **extracted,
            'raw_content': raw_yaml,
            'organization': user.organization,
            'repository': repo,
            'format': fmt_norm,
        }
        rule, _created = DetectionRule.objects.update_or_create(
            organization=user.organization,
            playbook=graph,
            format=fmt_norm,
            defaults=defaults
        )

        # Ensure initial author is the user performing first save, overriding YAML author only on creation
        if _created:
            rule.author = user.username or 'unknown'
            rule.save(update_fields=['author'])

        # Now inject workbench metadata using the rule's actual sigma_id (no duplicate UUID)
        raw_yaml_with_metadata = inject_metadata(
            rule_content=raw_yaml,
            rule_format=fmt_norm,
            author=(author or graph.author.username) if graph.author else (author or "Unknown"),
            rule_name=extracted['title'],
            description=description or extracted.get('description') or '',
            tags=tags or [],
            severity=graph.default_severity if graph.default_severity else "NA",
            status=graph.status if graph.status else "NA",
            mitre_technique=graph.mitre_technique.technique_id if graph.mitre_technique else "NA",
            rule_id=str(rule.sigma_id),
        )
        rule.raw_content = raw_yaml_with_metadata
        rule.save(update_fields=['raw_content'])

        # Also reflect latest saved content back on the workbench for display
        try:
            PlaybookGraph.objects.filter(pk=graph.id).update(detection_rule=raw_yaml)
        except Exception:
            pass

        invalidate_mgmt_cave_stats_cache(getattr(user.organization, 'id', None))

        filename = f"{slugify(extracted['title']) or 'rule'}.{get_format_spec(fmt_norm).file_extension}"
        return SaveDetectionRule(
            success=True,
            message="Rule saved to Library",
            rule=rule,
            commit_sha=None,
            errors=[],
            filename=filename,
        )


class GenerateAllRuleResult(graphene.ObjectType):
    format = graphene.String(required=True)
    status = graphene.String(required=True)
    method = graphene.String(required=True)
    content = graphene.String()
    error = graphene.String()


class GenerateAllDetectionRules(graphene.Mutation):
    class Arguments:
        source_format = graphene.String(required=True)
        source_content = graphene.String(required=True)
        target_formats = graphene.List(graphene.String, required=False)
        playbook_id = graphene.UUID(required=False)

    success = graphene.Boolean()
    results = graphene.List(GenerateAllRuleResult, required=True)

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, source_format, source_content, target_formats=None, playbook_id=None):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        src_fmt = normalize_rule_format(source_format)
        if not source_content or not source_content.strip():
            return GenerateAllDetectionRules(success=False, results=[])

        explicit_targets = [
            normalize_rule_format(f)
            for f in (target_formats or [])
            if normalize_rule_format(f) != src_fmt
        ]
        targets = explicit_targets or [fmt for fmt in FORMAT_REGISTRY.keys() if fmt not in ('OTHER', src_fmt)]
        logger.info(
            "Generate-all requested by user=%s org=%s playbook=%s source=%s targets=%s",
            getattr(user, 'username', 'unknown'),
            getattr(getattr(user, 'organization', None), 'id', None),
            str(playbook_id) if playbook_id else None,
            src_fmt,
            targets,
        )

        ai_user_settings = None
        playbook_context = None
        if targets:
            try:
                from ai_assistant.models import UserAISettings
                ai_user_settings = UserAISettings.objects.get(user=user)
            except Exception:
                ai_user_settings = None
            if playbook_id:
                try:
                    from ai_assistant.schema import _build_playbook_generation_context
                    playbook = PlaybookGraph.objects.prefetch_related('selected_capability_abstractions').get(
                        pk=playbook_id,
                        organization=user.organization,
                    )
                    playbook_context = _build_playbook_generation_context(playbook)
                except Exception:
                    logger.warning(
                        "Generate-all could not build playbook context for playbook=%s org=%s",
                        str(playbook_id),
                        getattr(getattr(user, 'organization', None), 'id', None),
                        exc_info=True,
                    )
                    playbook_context = None

        results = []
        for target_fmt in targets:
            converter_error = None
            try:
                converted = convert_rule_content(src_fmt, target_fmt, source_content)
            except Exception as exc:
                converted = None
                converter_error = str(exc)
                logger.exception(
                    "Generate-all converter failed source=%s target=%s playbook=%s",
                    src_fmt,
                    target_fmt,
                    str(playbook_id) if playbook_id else None,
                )
            if converted is not None:
                results.append(GenerateAllRuleResult(
                    format=target_fmt,
                    status='converted',
                    method='converter',
                    content=converted,
                    error=None,
                ))
                continue

            if not ai_user_settings:
                error_text = 'AI settings not configured'
                if converter_error:
                    error_text = f'Converter failed: {converter_error}; {error_text}'
                logger.warning(
                    "Generate-all failed without AI settings source=%s target=%s user=%s reason=%s",
                    src_fmt,
                    target_fmt,
                    getattr(user, 'username', 'unknown'),
                    error_text,
                )
                results.append(GenerateAllRuleResult(
                    format=target_fmt,
                    status='failed',
                    method='ai',
                    content=None,
                    error=error_text,
                ))
                continue

            try:
                from ai_assistant.engine import generate_similar_rules
                generated_text, _provider = generate_similar_rules(
                    ai_user_settings,
                    rule_content=source_content,
                    rule_format=src_fmt,
                    playbook_context=playbook_context,
                    variation_type='platform',
                    num_variations=1,
                    target_format=target_fmt,
                )
                generated_rule = (generated_text or '').split('---RULE---')[0].strip()
                if not generated_rule or generated_rule.lower().startswith('error'):
                    raise ValueError(generated_text or 'AI generation failed')
                results.append(GenerateAllRuleResult(
                    format=target_fmt,
                    status='generated',
                    method='ai',
                    content=generated_rule,
                    error=None,
                ))
            except Exception as exc:
                error_text = str(exc)
                if converter_error:
                    error_text = f"Converter failed: {converter_error}; AI failed: {error_text}"
                logger.exception(
                    "Generate-all AI generation failed source=%s target=%s playbook=%s user=%s error=%s",
                    src_fmt,
                    target_fmt,
                    str(playbook_id) if playbook_id else None,
                    getattr(user, 'username', 'unknown'),
                    error_text,
                )
                results.append(GenerateAllRuleResult(
                    format=target_fmt,
                    status='failed',
                    method='ai',
                    content=None,
                    error=error_text,
                ))

        logger.info(
            "Generate-all completed playbook=%s source=%s summary=%s",
            str(playbook_id) if playbook_id else None,
            src_fmt,
            [(r.format, r.status) for r in results],
        )
        return GenerateAllDetectionRules(
            success=any(r.status in ('converted', 'generated') for r in results),
            results=results,
        )


class SaveRuleInput(graphene.InputObjectType):
    format = graphene.String(required=True)
    content = graphene.String(required=True)


class SaveRuleResult(graphene.ObjectType):
    format = graphene.String(required=True)
    status = graphene.String(required=True)
    filename = graphene.String()
    message = graphene.String()


class SaveAllDetectionRules(graphene.Mutation):
    class Arguments:
        playbook_id = graphene.UUID(required=True)
        rules = graphene.List(SaveRuleInput, required=True)
        title = graphene.String(required=False)
        description = graphene.String(required=False)
        author = graphene.String(required=False)
        tags = graphene.List(graphene.String, required=False)
        auto_commit = graphene.Boolean(required=False, default_value=False)
        commit_message = graphene.String(required=False)

    success = graphene.Boolean()
    results = graphene.List(SaveRuleResult, required=True)

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, playbook_id, rules, title=None, description=None, author=None, tags=None, auto_commit=False, commit_message=None):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        results = []
        for entry in rules or []:
            raw_content = (entry.content or '').strip()
            fmt = normalize_rule_format(entry.format)
            if not raw_content:
                results.append(SaveRuleResult(format=fmt, status='skipped', filename=None, message='Empty content'))
                continue
            saved = SaveDetectionRule.mutate(
                root,
                info,
                playbook_id=playbook_id,
                raw_yaml=raw_content,
                format=fmt,
                title=title,
                description=description,
                author=author,
                tags=tags,
                auto_commit=auto_commit,
                commit_message=commit_message,
            )
            results.append(SaveRuleResult(
                format=fmt,
                status='saved' if saved.success else 'failed',
                filename=getattr(saved, 'filename', None),
                message=saved.message,
            ))

        return SaveAllDetectionRules(
            success=all(r.status in ('saved', 'skipped') for r in results),
            results=results,
        )


# --- New: UpsertRule mutation ---
class UpsertRule(graphene.Mutation):
    class Arguments:
        repo_id = graphene.ID(required=True)
        title = graphene.String(required=True)
        status = graphene.String()
        description = graphene.String()
        author = graphene.String()
        references = graphene.List(graphene.String)
        logsource = graphene.JSONString()
        detection = graphene.JSONString()
        falsePositives = graphene.List(graphene.String)
        level = graphene.String()
        tags = graphene.List(graphene.String)
        rawContent = graphene.String(description="Original rule content (YAML, KQL, etc.)")
        format = graphene.String(description="Rule format: KQL, EQL, WAZUH, SPL, AQL, or OTHER")

    rule = graphene.Field(RuleType)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, repo_id, title, **kwargs):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        # Service accounts can access any repository for cross-org sync
        is_service_account = hasattr(user, 'username') and ('service' in user.username.lower() or user.username == 'connector_svc')

        try:
            if is_service_account:
                repo = RuleRepository.objects.get(pk=repo_id)
            else:
                repo = RuleRepository.objects.get(pk=repo_id, organization=user.organization)
        except RuleRepository.DoesNotExist:
            raise Exception("Repository not found")

        # For service accounts, use the repository's organization
        target_org = repo.organization if is_service_account else user.organization

        # Prefer original YAML content if provided by connector; otherwise fall back to JSON parts
        raw_content = kwargs.get('rawContent')
        if raw_content is None:
            raw_parts = {}
            for key in ("logsource", "detection"):
                if key in kwargs and kwargs[key] is not None:
                    raw_parts[key] = kwargs[key]
            raw_content = json.dumps(raw_parts) if raw_parts else None

        # Validate and set format
        rule_format = kwargs.get('format', 'OTHER').upper()
        if rule_format not in ['KQL', 'EQL', 'WAZUH', 'SPL', 'AQL', 'OTHER']:
            rule_format = 'OTHER'

        defaults = {
            'organization': target_org,
            'repository': repo,
            'description': kwargs.get('description'),
            'author': kwargs.get('author'),
            'status': kwargs.get('status'),
            'raw_content': raw_content,
            'format': rule_format,
        }

        rule, _created = DetectionRule.objects.update_or_create(
            organization=target_org,
            title=title,
            defaults=defaults
        )
        # Publish rule.created or rule.updated for admin/owner notifications
        try:
            publisher = get_publisher()
            publisher.publish_message('rule.created' if _created else 'rule.updated', {
                'rule_id': str(rule.id),
                'title': rule.title,
                'organization_id': str(target_org.id),
                'actor_id': str(user.id),
                'creator_id': str(getattr(rule.playbook.author, 'id', '')) if getattr(rule, 'playbook', None) else None,
            })
        except Exception:
            pass
        invalidate_mgmt_cave_stats_cache(getattr(target_org, 'id', None))
        return UpsertRule(rule=rule)


class PushPlaybookToGit(graphene.Mutation):
    class Arguments:
        graphId = graphene.UUID(required=True)
        repositoryId = graphene.String(required=True)
        targetFolder = graphene.String(required=False, description="Target folder path in the repository (e.g., 'rules/sigma', 'rules/kql'). Will be created if it doesn't exist.")

    ok = graphene.Boolean()
    queued_count = graphene.Int(description="Number of rules enqueued for push")
    message = graphene.String()

    class Meta:
        description = "Publishes events to RabbitMQ to push detection rules to Git. Only rules (ideally newly created or recently edited) are sent."

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, graphId, repositoryId, targetFolder=None):
        logger.info(f"PushPlaybookToGit called with graphId={graphId}, repositoryId={repositoryId}, targetFolder={targetFolder}")
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        # --- Security Check 1: Verify user owns the Workbench/Graph ---
        try:
            graph = PlaybookGraph.objects.get(pk=graphId, organization=user.organization)
        except PlaybookGraph.DoesNotExist:
            raise Exception("Workbench not found or you do not have permission")

        # --- Business Rule: Only APPROVED or DEPLOYED graphs can be pushed ---
        allowed_statuses = {
            getattr(DetectionPlaybook.PlaybookStatus, 'APPROVED', 'APPROVED'),
            getattr(DetectionPlaybook.PlaybookStatus, 'DEPLOYED', 'DEPLOYED')
        }
        if (graph.status or '').upper() not in {str(s).upper() for s in allowed_statuses}:
            raise Exception("Only APPROVED or DEPLOYED workbenches can be pushed")

        # --- Security Check 2: Verify user owns the repository ---
        try:
            repo = RuleRepository.objects.get(pk=repositoryId, organization=user.organization)
        except RuleRepository.DoesNotExist:
            raise Exception("Repository not found or you do not have permission")

        # --- Determine which rules to push ---
        # Base queryset: rules in the selected repository and org
        rules_qs = DetectionRule.objects.filter(
            organization=user.organization,
            repository=repo,
        )
        # Optional: restrict to the rule linked to this playbook graph (if any)
        if graph:
            rules_qs = rules_qs.filter(playbook=graph)

        # Prefer only rules that are new or updated since the repo's last sync
        last_sync = repo.last_synced
        if last_sync:
            from django.db.models import Q
            rules_qs = rules_qs.filter(Q(updated_at__gt=last_sync) | Q(created_at__gt=last_sync))

        rules = list(rules_qs)

        if not rules:
            # Nothing to push; succeed no-op
            return PushPlaybookToGit(ok=True, queued_count=0, message="No rules to push (no changes since last sync)")

        # --- Publish one message per rule to RabbitMQ ---
        publisher = get_publisher()
        routing_key = "playbook.git.push.requested"  # Connector listens to this key in our setup

        for rule in rules:
            payload = {
                "action": "push_rule",
                "organization_id": str(user.organization.id),
                "repository_id": str(repo.id),
                "rule_id": str(rule.id),
                # Minimal config for connector; token is decrypted via property
                "config": {
                    "url": repo.git_url,
                    "token": repo.token,
                    "username": repo.username,
                },
                # Rule content for writer
                "rule": {
                    "title": rule.title,
                    "rule_content": rule.raw_content,
                    "author_name": rule.author or (getattr(user, 'username', None) or 'unknown'),
                    "format": rule.format or 'OTHER',  # Include the rule format
                },
                "target_folder": targetFolder,  # Target folder path for organization
                "triggered_by_user_id": str(user.id),
            }
            try:
                publisher.publish_message(routing_key, payload)
            except Exception as e:
                logger.error(f"Failed to queue push for rule {rule.id}: {e}")
                return PushPlaybookToGit(
                    ok=False,
                    queued_count=0,
                    message=f"Failed to queue push request: {str(e)}"
                )

        return PushPlaybookToGit(ok=True, queued_count=len(rules), message=f"Queued {len(rules)} rule(s) for push")


# --- Sigma Rule Conversion Types ---
class UpdateDetectionRule(graphene.Mutation):
    """Update a detection rule's content directly from the Rule Hub."""
    class Arguments:
        rule_id = graphene.ID(required=True)
        raw_content = graphene.String(required=True, description="Updated rule content")

    success = graphene.Boolean()
    message = graphene.String()
    rule = graphene.Field(RuleType)

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, rule_id, raw_content):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        try:
            rule = DetectionRule.objects.get(pk=rule_id, organization=user.organization)
        except DetectionRule.DoesNotExist:
            raise Exception("Rule not found or you do not have permission")

        # Only author, admin, or superadmin can edit
        is_owner = rule.author == user.username
        is_admin_or_super = user.role == Roles.ADMIN or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)
        if not (is_owner or is_admin_or_super):
            raise Exception("Only the rule author, admin, or superadmin can edit this rule")

        # Re-detect format and re-parse metadata from updated content
        detected_fmt = detect_rule_format(raw_content)
        fmt = detected_fmt if detected_fmt in ('KQL', 'EQL', 'WAZUH', 'SPL', 'AQL', 'OTHER') else rule.format
        try:
            extracted = parse_rule_by_format(raw_content, fmt, fallback_author=rule.author or '')
        except ValueError:
            extracted = {}

        rule.raw_content = raw_content
        rule.format = fmt
        if extracted.get('title'):
            rule.title = extracted['title']
        if extracted.get('description'):
            rule.description = extracted['description']
        if extracted.get('status'):
            rule.status = extracted['status']
        rule.save()

        invalidate_mgmt_cave_stats_cache(getattr(user.organization, 'id', None))

        return UpdateDetectionRule(success=True, message="Rule updated successfully", rule=rule)


class DeleteDetectionRule(graphene.Mutation):
    """Delete a detection rule from the library.

    Rules can only be deleted if:
    - The linked workbench (if any) is NOT in DEPLOYED status
    - User is the rule author, admin, or superuser
    """
    class Arguments:
        rule_id = graphene.UUID(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, rule_id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        try:
            rule = DetectionRule.objects.get(pk=rule_id, organization=user.organization)
        except DetectionRule.DoesNotExist:
            raise Exception("Rule not found or you do not have permission")

        # Check if user is author, admin, or superuser
        is_owner = rule.author == user.username
        is_admin_or_super = user.role == Roles.ADMIN or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)

        if not (is_owner or is_admin_or_super):
            raise Exception("Only the rule author, admin, or superadmin can delete this rule")

        # If rule is linked to a playbook, check that playbook is not DEPLOYED
        if rule.playbook:
            playbook_status = (rule.playbook.status or '').upper()
            if playbook_status == 'DEPLOYED':
                raise Exception("Cannot delete rule: the linked workbench is in DEPLOYED status. Please undeploy it first.")

        # Delete the rule
        org_id = getattr(rule.organization, 'id', None)
        rule.delete()
        invalidate_mgmt_cave_stats_cache(org_id)
        return DeleteDetectionRule(success=True, message="Rule deleted successfully")


class Mutation(graphene.ObjectType):
    create_rule_repository = CreateRuleRepository.Field()
    update_rule_repository = UpdateRuleRepository.Field()
    delete_rule_repository = DeleteRuleRepository.Field()
    pull_rule_repository = PullRuleRepository.Field()
    sync_rule_repository_rag = SyncRuleRepositoryRag.Field()
    upsert_rule = UpsertRule.Field()
    push_playbook_to_git = PushPlaybookToGit.Field()
    save_detection_rule = SaveDetectionRule.Field()
    save_all_detection_rules = SaveAllDetectionRules.Field()
    generate_all_detection_rules = GenerateAllDetectionRules.Field()
    update_detection_rule = UpdateDetectionRule.Field()
    delete_detection_rule = DeleteDetectionRule.Field()
    get_autocomplete_options = GetAutocompleteOptions.Field()
    validate_rule_content = ValidateRuleContent.Field()


# ---------------------------------------------------------------------------
# DeployOpenTideRule – parallel API deployment to multiple platforms
# ---------------------------------------------------------------------------

class PlatformDeploymentResultType(graphene.ObjectType):
    """Per-platform deployment outcome."""
    platform = graphene.String()
    success = graphene.Boolean()
    rule_id = graphene.String()
    message = graphene.String()
    errors = graphene.List(graphene.String)


class DeployOpenTideRule(graphene.Mutation):
    """
    Deploy an OpenTide rule to one or more SIEM/EDR platforms in parallel.

    Reads platform credentials stored in the ``PlatformCredential`` model
    (scoped to the calling user's organisation), authenticates via each
    platform's native OAuth/JWT/token mechanism, and deploys the rule.

    Returns a list of per-platform results.
    """

    class Arguments:
        rule_id = graphene.UUID(required=True, description="DetectionRule UUID")
        platforms = graphene.List(
            graphene.String,
            required=True,
            description="Platform keys to deploy to (defender, sentinel, splunk, qradar, wazuh)",
        )

    results = graphene.List(PlatformDeploymentResultType)
    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, rule_id, platforms):
        import concurrent.futures
        import yaml as _yaml
        from organizations.models import PlatformCredential
        from .deployers import PLATFORM_DEPLOYER_MAP, DeploymentResult

        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        # Load the rule
        try:
            rule = DetectionRule.objects.get(pk=rule_id, organization=user.organization)
        except DetectionRule.DoesNotExist:
            raise Exception("Rule not found or you do not have permission")

        if rule.format != 'OPENTIDE':
            raise Exception("Only OPENTIDE-format rules can be deployed via this mutation")

        # Parse YAML
        try:
            rule_data = _yaml.safe_load(rule.raw_content) or {}
        except Exception as exc:
            raise Exception(f"Failed to parse rule YAML: {exc}")

        # Validate requested platforms
        valid_platforms = set(PLATFORM_DEPLOYER_MAP.keys())
        requested = [p.lower() for p in (platforms or [])]
        unknown = [p for p in requested if p not in valid_platforms]
        if unknown:
            raise Exception(f"Unknown platform(s): {', '.join(unknown)}")

        # Load credentials for the organisation
        cred_map = PlatformCredential.preferred_credentials_map(
            organization=user.organization,
            platforms=requested,
        )

        # Build deployer instances (skip platforms without credentials)
        deployers: list[tuple[str, object]] = []
        skipped_results: list[DeploymentResult] = []
        for platform_key in requested:
            if platform_key not in cred_map:
                skipped_results.append(
                    DeploymentResult(
                        platform=PLATFORM_DEPLOYER_MAP[platform_key].PLATFORM_NAME,
                        success=False,
                        message=f"No credentials configured for {platform_key}. "
                                "Please add credentials via the platform settings.",
                    )
                )
                continue
            deployer_cls = PLATFORM_DEPLOYER_MAP[platform_key]
            deployers.append((platform_key, deployer_cls(cred_map[platform_key])))

        # Execute deployments in parallel
        outcomes: list[DeploymentResult] = list(skipped_results)

        def _run_deployer(item):
            _, deployer = item
            return deployer.run(rule_data)

        if deployers:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(deployers)) as pool:
                for result in pool.map(_run_deployer, deployers):
                    outcomes.append(result)

        # Convert to GraphQL types
        gql_results = [
            PlatformDeploymentResultType(
                platform=r.platform,
                success=r.success,
                rule_id=r.rule_id,
                message=r.message,
                errors=r.errors or [],
            )
            for r in outcomes
        ]

        overall_success = all(r.success for r in outcomes)
        message = (
            f"Deployed to {sum(r.success for r in outcomes)}/{len(outcomes)} platform(s) successfully."
        )
        logger.info('[DeployOpenTideRule] rule=%s %s', rule_id, message)
        return DeployOpenTideRule(results=gql_results, success=overall_success, message=message)


# --- New: Update last_sync timestamp on a repository ---
class UpdateRuleRepositoryLastSync(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    repository = graphene.Field(RuleRepositoryType)

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        # Service accounts can access any repository for cross-org sync
        is_service_account = hasattr(user, 'username') and ('service' in user.username.lower() or user.username == 'connector_svc')

        try:
            if is_service_account:
                repo = RuleRepository.objects.get(pk=id)
            else:
                repo = RuleRepository.objects.get(pk=id, organization=user.organization)
        except RuleRepository.DoesNotExist:
            raise Exception("Repository not found")

        repo.last_synced = timezone.now()
        repo.save(update_fields=["last_synced"])
        return UpdateRuleRepositoryLastSync(repository=repo)


class UpdateRuleRepositoryRagSyncStatus(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        status = graphene.String(required=True)
        error_message = graphene.String(required=False)
        synced_templates = graphene.Int(required=False)

    repository = graphene.Field(RuleRepositoryType)

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, id, status, error_message=None, synced_templates=None):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        is_service_account = hasattr(user, 'username') and ('service' in user.username.lower() or user.username == 'connector_svc')

        try:
            if is_service_account:
                repo = RuleRepository.objects.get(pk=id)
            else:
                repo = RuleRepository.objects.get(pk=id, organization=user.organization)
        except RuleRepository.DoesNotExist:
            raise Exception("Repository not found")

        next_status = (status or '').upper()
        allowed_statuses = {choice[0] for choice in RuleRepository.RAGSyncStatus.choices}
        if next_status not in allowed_statuses:
            raise Exception(f"Invalid RAG sync status '{next_status}'")

        status_updated_at = timezone.now()
        update_fields = ['rag_last_sync_status', 'rag_last_sync_status_at']
        repo.rag_last_sync_status = next_status
        repo.rag_last_sync_status_at = status_updated_at

        if error_message is not None:
            repo.rag_last_sync_error = error_message.strip()
            update_fields.append('rag_last_sync_error')
        elif next_status in {
            RuleRepository.RAGSyncStatus.SUCCESS,
            RuleRepository.RAGSyncStatus.PARTIAL,
        }:
            repo.rag_last_sync_error = ''
            update_fields.append('rag_last_sync_error')

        if synced_templates is not None:
            repo.rag_last_synced_templates = max(int(synced_templates), 0)
            update_fields.append('rag_last_synced_templates')

        if next_status in {
            RuleRepository.RAGSyncStatus.PARTIAL,
            RuleRepository.RAGSyncStatus.SUCCESS,
            RuleRepository.RAGSyncStatus.FAILED,
        }:
            repo.rag_last_synced = timezone.now()
            update_fields.append('rag_last_synced')

        repo.save(update_fields=list(dict.fromkeys(update_fields)))
        return UpdateRuleRepositoryRagSyncStatus(repository=repo)


class UpdateRuleRepositoryRagFileStatuses(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        files = graphene.JSONString(required=True)
        replace_existing = graphene.Boolean(required=False, default_value=False)

    ok = graphene.Boolean()
    count = graphene.Int()
    repository = graphene.Field(RuleRepositoryType)

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, id, files, replace_existing=False):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication required")

        is_service_account = hasattr(user, 'username') and ('service' in user.username.lower() or user.username == 'connector_svc')

        try:
            if is_service_account:
                repo = RuleRepository.objects.get(pk=id)
            else:
                repo = RuleRepository.objects.get(pk=id, organization=user.organization)
        except RuleRepository.DoesNotExist:
            raise Exception("Repository not found")

        parsed_files = files
        if isinstance(parsed_files, str):
            try:
                parsed_files = json.loads(parsed_files)
            except Exception as exc:
                raise Exception(f"Invalid files JSON payload: {exc}")

        if not isinstance(parsed_files, list):
            raise Exception("files must be a list of file status objects")

        allowed_statuses = {choice[0] for choice in RuleRepositoryRAGFileStatus.IngestionStatus.choices}
        now = timezone.now()
        updated_count = 0
        seen_keys = set()

        for item in parsed_files:
            if not isinstance(item, dict):
                continue

            source_path = (item.get('source_path') or item.get('sourcePath') or '').strip()
            if not source_path:
                continue

            source_branch = (item.get('source_branch') or item.get('sourceBranch') or repo.rag_branch or 'main').strip() or 'main'
            language = (item.get('language') or 'KQL').upper()
            ingestion_status = (item.get('ingestion_status') or item.get('ingestionStatus') or 'FAILED').upper()
            if ingestion_status not in allowed_statuses:
                ingestion_status = RuleRepositoryRAGFileStatus.IngestionStatus.FAILED

            templates_raw = item.get('templates_count') if item.get('templates_count') is not None else item.get('templatesCount')
            try:
                templates_count = max(int(templates_raw or 0), 0)
            except Exception:
                templates_count = 0

            error_message = (item.get('error_message') if item.get('error_message') is not None else item.get('errorMessage'))
            error_message = (error_message or '').strip()
            if ingestion_status == RuleRepositoryRAGFileStatus.IngestionStatus.INGESTED and not error_message:
                error_message = ''

            RuleRepositoryRAGFileStatus.objects.update_or_create(
                repository=repo,
                source_path=source_path,
                source_branch=source_branch,
                language=language,
                defaults={
                    'ingestion_status': ingestion_status,
                    'templates_count': templates_count,
                    'last_synced_at': now,
                    'last_error': error_message,
                },
            )

            seen_keys.add((source_path, source_branch, language))
            updated_count += 1

        if replace_existing:
            stale_qs = RuleRepositoryRAGFileStatus.objects.filter(repository=repo)
            for stale in stale_qs:
                stale_key = (stale.source_path, stale.source_branch, (stale.language or 'KQL').upper())
                if stale_key not in seen_keys:
                    stale.delete()

        return UpdateRuleRepositoryRagFileStatuses(ok=True, count=updated_count, repository=repo)


# Extend Mutation with the new field
class Mutation(Mutation, graphene.ObjectType):
    update_rule_repository_last_sync = UpdateRuleRepositoryLastSync.Field()
    update_rule_repository_rag_sync_status = UpdateRuleRepositoryRagSyncStatus.Field()
    update_rule_repository_rag_file_statuses = UpdateRuleRepositoryRagFileStatuses.Field()
    deploy_open_tide_rule = DeployOpenTideRule.Field()
