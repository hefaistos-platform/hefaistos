import json
import graphene
import uuid as _uuid
from django.core.cache import cache
from django.db import models
from django.db import transaction
from django.utils import timezone
from graphene_django import DjangoObjectType
from graphql import GraphQLError
from .chokepoints_sync import (
    DEFAULT_CHOKEPOINTS_REF,
    DEFAULT_CHOKEPOINTS_REPO,
    fetch_latest_ref_sha,
    normalize_git_ref,
)
from .scraper import (
    scrape_mitre_analytic_details,
    scrape_mitre_log_sources_json,
)
from .models import (
    MitreAttackTechnique, MitreDataSource, MitreDataComponent,
    MitreAnalytic, MitreDetectionStrategy,
    D3fendDefensiveTechnique, D3fendDigitalArtifact, D3fendAttackMapping,
    ShareTideIndexEntry, PlatformDataVersion, MitreImportJob,
    ChokepointSnapshot, ChokepointEntry, ChokepointImportJob,
)
from playbooks.models import PlaybookGraph

# --- TYPES ---

class MitreAnalyticType(DjangoObjectType):
    class Meta:
        model = MitreAnalytic
        fields = ("id", "stix_id", "name", "description")

class MitreDetectionStrategyType(DjangoObjectType):
    analytics = graphene.List(MitreAnalyticType)

    class Meta:
        model = MitreDetectionStrategy
        fields = ("id", "def_id", "name", "url", "analytics")

    def resolve_analytics(self, info):
        return self.analytics.all()

class MitreDataSourceType(DjangoObjectType):
    class Meta:
        model = MitreDataSource
        fields = ("id", "stix_id", "name", "description")

class MitreDataComponentType(DjangoObjectType):
    data_source = graphene.Field(MitreDataSourceType)

    class Meta:
        model = MitreDataComponent
        fields = ("id", "stix_id", "name", "description", "data_source")

class MitreAttackTechniqueType(DjangoObjectType):
    data_components = graphene.List(MitreDataComponentType)
    detection_strategies = graphene.List(MitreDetectionStrategyType)

    class Meta:
        model = MitreAttackTechnique
        fields = ("id", "technique_id", "name", "url", "description", "tactic", "revoked", "deprecated")

    def resolve_data_components(self, info):
        return self.data_components.all()

    def resolve_detection_strategies(self, info):
        return self.detection_strategies.all()


class PlatformDataVersionType(graphene.ObjectType):
    """Framework version currently loaded in the database."""
    framework = graphene.String()
    version = graphene.String()
    imported_at = graphene.String()


class MitreImportJobType(DjangoObjectType):
    """An async MITRE ATT&CK import job."""
    duration_seconds = graphene.Float(description="Wall-clock duration in seconds, or null if not finished.")

    class Meta:
        model = MitreImportJob
        fields = (
            "id", "version", "mode", "status", "log", "error",
            "created_at", "updated_at", "started_at", "finished_at",
            "triggered_by",
        )

    def resolve_duration_seconds(self, info):
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


class ChokepointSnapshotType(DjangoObjectType):
    class Meta:
        model = ChokepointSnapshot
        fields = (
            "id", "source_repo", "source_ref", "source_sha", "status",
            "summary", "entry_count", "validation_errors",
            "created_at", "updated_at", "activated_at", "triggered_by",
        )


class ChokepointImportJobType(DjangoObjectType):
    duration_seconds = graphene.Float(description="Wall-clock duration in seconds, or null if not finished.")

    class Meta:
        model = ChokepointImportJob
        fields = (
            "id", "source_repo", "source_ref", "mode", "status", "summary",
            "log", "error", "created_at", "updated_at", "started_at",
            "finished_at", "snapshot", "triggered_by",
        )

    def resolve_duration_seconds(self, info):
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


class ChokepointDiffSummaryType(graphene.ObjectType):
    snapshot_id = graphene.UUID()
    active_snapshot_id = graphene.UUID()
    added = graphene.Int()
    changed = graphene.Int()
    removed = graphene.Int()
    unchanged = graphene.Int()
    staged_count = graphene.Int()
    active_count = graphene.Int()

# --- QUERY ---

class SuggestionResultType(graphene.ObjectType):
    """
    A hybrid object that groups data for the UI.
    """
    technique = graphene.Field(MitreAttackTechniqueType)
    strategies = graphene.List(MitreDetectionStrategyType)
    data_components = graphene.List(MitreDataComponentType)

class MitreLogSourceData(graphene.ObjectType):
    data_component = graphene.String()
    log_provider = graphene.String()
    channel = graphene.String()


# --- D3FEND TYPES ---

class D3fendArtifactType(DjangoObjectType):
    class Meta:
        model = D3fendDigitalArtifact
        fields = ("id", "artifact_id", "name", "definition", "iri")


class D3fendTechniqueType(DjangoObjectType):
    digital_artifacts = graphene.List(D3fendArtifactType)
    countered_attacks = graphene.List(MitreAttackTechniqueType)
    
    class Meta:
        model = D3fendDefensiveTechnique
        fields = ("id", "d3fend_id", "name", "definition", "iri", "tactic", "parent")
    
    def resolve_digital_artifacts(self, info):
        return self.digital_artifacts.all()
    
    def resolve_countered_attacks(self, info):
        # Get ATT&CK techniques this D3FEND technique counters
        mappings = D3fendAttackMapping.objects.filter(d3fend_technique=self).select_related('attack_technique')
        return [mapping.attack_technique for mapping in mappings]


class D3fendGapAnalysisType(graphene.ObjectType):
    """Gap analysis for an ATT&CK technique showing D3FEND coverage"""
    attack_technique = graphene.Field(MitreAttackTechniqueType)
    recommended_countermeasures = graphene.List(D3fendTechniqueType)
    current_coverage = graphene.List(D3fendTechniqueType)
    gaps = graphene.List(D3fendTechniqueType)
    coverage_percentage = graphene.Float()


class D3fendCoverageTechniqueType(graphene.ObjectType):
    """D3FEND technique with coverage status"""
    technique = graphene.Field(D3fendTechniqueType)
    is_covered = graphene.Boolean()
    implementing_playbooks = graphene.List(graphene.String)  # List of playbook titles


class D3fendCoverageMatrixType(graphene.ObjectType):
    """Full D3FEND coverage matrix organized by tactic"""
    tactic = graphene.String()
    techniques = graphene.List(D3fendCoverageTechniqueType)


# ---------------------------------------------------------------------------
# ShareTide Index Types
# ---------------------------------------------------------------------------

class ShareTideIndexEntryType(DjangoObjectType):
    """A single ShareTide vocabulary index entry."""

    class Meta:
        model = ShareTideIndexEntry
        fields = ("id", "category", "value", "description", "source_url", "sort_order")


def _require_superuser(info):
    user = info.context.user
    if user.is_anonymous:
        raise GraphQLError("Authentication required")
    if not user.is_superuser:
        raise GraphQLError("Permission denied. Superuser access required.")
    return user


@transaction.atomic
def _activate_chokepoint_snapshot(snapshot: ChokepointSnapshot) -> ChokepointSnapshot:
    """
    Promote a snapshot as ACTIVE and archive any previously active snapshot.
    """
    active_qs = (
        ChokepointSnapshot.objects.select_for_update()
        .filter(status=ChokepointSnapshot.Status.ACTIVE)
        .exclude(id=snapshot.id)
    )
    active_qs.update(status=ChokepointSnapshot.Status.ARCHIVED)

    snapshot.status = ChokepointSnapshot.Status.ACTIVE
    snapshot.activated_at = timezone.now()
    snapshot.save(update_fields=["status", "activated_at", "updated_at"])

    version_value = (snapshot.source_sha[:12] if snapshot.source_sha else snapshot.source_ref)[:20] or "staged"
    PlatformDataVersion.objects.update_or_create(
        framework='detection-chokepoints',
        defaults={'version': version_value},
    )
    return snapshot


class Query(graphene.ObjectType):
    detection_suggestions = graphene.Field(
        SuggestionResultType,
        technique_id=graphene.String(required=True),
        description="Returns Strategies, Analytics, and Data Components for a Technique."
    )

    search_techniques = graphene.List(
        MitreAttackTechniqueType,
        search=graphene.String(required=True),
        include_revoked=graphene.Boolean(
            default_value=False,
            description="When true, include revoked and deprecated techniques in results",
        ),
    )

    sharetide_index_entries = graphene.List(
        ShareTideIndexEntryType,
        category=graphene.String(description="Filter by category, e.g. 'bdr_platforms'"),
        description=(
            "Return ShareTide vocabulary index entries. "
            "Optionally filter by category (e.g. 'bdr_platforms', 'mdr_responders')."
        ),
    )
    enrich_analytic_data = graphene.String(
        strategy_url=graphene.String(required=True),
        analytic_id=graphene.String(required=True),
        description="Scrapes MITRE website for Mutable Elements and Log Sources"
    )

    # JSON rows for interactive UI table
    enrich_analytic_json = graphene.List(
        MitreLogSourceData,
        strategy_url=graphene.String(required=True),
        analytic_id=graphene.String(required=True),
        description="Returns list of {dataComponent, logProvider, channel} for an analytic"
    )

    attack_navigator_layer = graphene.String(
        description="Returns a MITRE Navigator Layer JSON string for Deployed Playbooks"
    )

    loaded_attack_versions = graphene.List(
        PlatformDataVersionType,
        description="Returns the ATT&CK / D3FEND versions currently loaded in the database",
    )

    latest_available_attack_version = graphene.String(
        description=(
            "Fetches the latest published ATT&CK version tag from GitHub "
            "(cached 1 hour).  Returns null on network errors."
        ),
    )

    mitre_import_job = graphene.Field(
        MitreImportJobType,
        id=graphene.UUID(required=True),
        description="Get a single MitreImportJob by ID.",
    )

    mitre_import_jobs = graphene.List(
        MitreImportJobType,
        limit=graphene.Int(default_value=20),
        description="List recent MITRE import jobs, newest first.",
    )

    latest_available_chokepoint_revision = graphene.String(
        source_repo=graphene.String(default_value=DEFAULT_CHOKEPOINTS_REPO),
        ref=graphene.String(default_value=DEFAULT_CHOKEPOINTS_REF),
        description=(
            "Resolve latest commit SHA for detection-chokepoints source ref "
            "(cached 1 hour). Returns null on network errors."
        ),
    )

    active_chokepoint_snapshot = graphene.Field(
        ChokepointSnapshotType,
        description="Currently active chokepoint snapshot.",
    )

    chokepoint_snapshot = graphene.Field(
        ChokepointSnapshotType,
        id=graphene.UUID(required=True),
        description="Get a single chokepoint snapshot by ID.",
    )

    chokepoint_snapshots = graphene.List(
        ChokepointSnapshotType,
        status=graphene.String(),
        limit=graphene.Int(default_value=20),
        description="List chokepoint snapshots (latest first).",
    )

    chokepoint_import_job = graphene.Field(
        ChokepointImportJobType,
        id=graphene.UUID(required=True),
        description="Get a single chokepoint import job by ID.",
    )

    chokepoint_import_jobs = graphene.List(
        ChokepointImportJobType,
        limit=graphene.Int(default_value=20),
        description="List recent chokepoint import jobs, newest first.",
    )

    staged_chokepoint_diff = graphene.Field(
        ChokepointDiffSummaryType,
        snapshot_id=graphene.UUID(required=True),
        description="Compare a staged snapshot to current active snapshot.",
    )

    # D3FEND Queries
    all_d3fend_techniques = graphene.List(
        D3fendTechniqueType,
        search=graphene.String(),
        tactic=graphene.String(),
        limit=graphene.Int(),
        offset=graphene.Int(),
        description="List/search D3FEND techniques"
    )

    d3fend_technique = graphene.Field(
        D3fendTechniqueType,
        id=graphene.ID(required=True),
        description="Get single D3FEND technique with related artifacts"
    )

    d3fend_gap_analysis = graphene.Field(
        D3fendGapAnalysisType,
        attack_technique_id=graphene.String(required=True),
        description="Get D3FEND coverage gaps for an ATT&CK technique"
    )

    d3fend_coverage_matrix = graphene.List(
        D3fendCoverageMatrixType,
        description="Full D3FEND coverage matrix for visualization"
    )

    def resolve_detection_suggestions(self, info, technique_id):
        clean_id = technique_id.strip()
        try:
            # Case-insensitive lookup; exclude revoked/deprecated from suggestions
            technique = MitreAttackTechnique.objects.get(
                technique_id__iexact=clean_id,
                revoked=False,
                deprecated=False,
            )
        except MitreAttackTechnique.DoesNotExist:
            return None

        return SuggestionResultType(
            technique=technique,
            # 1. Strategies -> Analytics
            strategies=technique.detection_strategies.all().prefetch_related('analytics'),
            # 2. Data Components -> Data Sources
            data_components=technique.data_components.all().select_related('data_source')
        )

    def resolve_search_techniques(self, info, search, include_revoked=False):
        qs = (
            MitreAttackTechnique.objects.filter(name__icontains=search)
            | MitreAttackTechnique.objects.filter(technique_id__icontains=search)
        )
        if not include_revoked:
            qs = qs.filter(revoked=False, deprecated=False)
        return qs

    def resolve_loaded_attack_versions(self, info):
        rows = PlatformDataVersion.objects.all().order_by('framework')
        return [
            PlatformDataVersionType(
                framework=r.framework,
                version=r.version,
                imported_at=r.imported_at.isoformat() if r.imported_at else None,
            )
            for r in rows
        ]

    def resolve_latest_available_attack_version(self, info):
        cache_key = "mitre:latest_attack_version"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            import re
            import requests as _req
            resp = _req.get(
                "https://api.github.com/repos/mitre-attack/attack-stix-data/tags",
                timeout=5,
                headers={"Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            tags = resp.json()
            versions = []
            for tag in tags:
                name = tag.get("name", "")
                clean = re.sub(r"^(ATT&CK-v|v)", "", name)
                if re.match(r"^\d+\.\d+$", clean):
                    versions.append(clean)
            if not versions:
                return None
            versions.sort(key=lambda v: [int(x) for x in v.split(".")])
            result = versions[-1]
            cache.set(cache_key, result, timeout=3600)
            return result
        except Exception:
            return None

    def resolve_mitre_import_job(self, info, id):
        _require_superuser(info)
        try:
            return MitreImportJob.objects.get(id=id)
        except MitreImportJob.DoesNotExist:
            return None

    def resolve_mitre_import_jobs(self, info, limit=20):
        _require_superuser(info)
        return MitreImportJob.objects.all()[:limit]

    def resolve_latest_available_chokepoint_revision(
        self,
        info,
        source_repo=DEFAULT_CHOKEPOINTS_REPO,
        ref=DEFAULT_CHOKEPOINTS_REF,
    ):
        cache_key = f"chokepoints:latest_revision:{source_repo}:{ref}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            resolved = fetch_latest_ref_sha(source_repo, normalize_git_ref(ref))
            cache.set(cache_key, resolved, timeout=3600)
            return resolved
        except Exception:
            return None

    def resolve_active_chokepoint_snapshot(self, info):
        _require_superuser(info)
        return ChokepointSnapshot.objects.filter(status=ChokepointSnapshot.Status.ACTIVE).first()

    def resolve_chokepoint_snapshot(self, info, id):
        _require_superuser(info)
        try:
            return ChokepointSnapshot.objects.get(id=id)
        except ChokepointSnapshot.DoesNotExist:
            return None

    def resolve_chokepoint_snapshots(self, info, status=None, limit=20):
        _require_superuser(info)
        qs = ChokepointSnapshot.objects.all()
        if status:
            status_upper = str(status).upper()
            if status_upper in ChokepointSnapshot.Status.values:
                qs = qs.filter(status=status_upper)
        return qs[:limit]

    def resolve_chokepoint_import_job(self, info, id):
        _require_superuser(info)
        try:
            return ChokepointImportJob.objects.get(id=id)
        except ChokepointImportJob.DoesNotExist:
            return None

    def resolve_chokepoint_import_jobs(self, info, limit=20):
        _require_superuser(info)
        return ChokepointImportJob.objects.select_related("snapshot", "triggered_by").all()[:limit]

    def resolve_staged_chokepoint_diff(self, info, snapshot_id):
        _require_superuser(info)
        try:
            staged = ChokepointSnapshot.objects.get(id=snapshot_id)
        except ChokepointSnapshot.DoesNotExist:
            return None

        active = (
            ChokepointSnapshot.objects
            .filter(status=ChokepointSnapshot.Status.ACTIVE)
            .exclude(id=staged.id)
            .order_by("-activated_at", "-created_at")
            .first()
        )

        staged_rows = dict(
            ChokepointEntry.objects.filter(snapshot=staged).values_list("entry_key", "source_hash")
        )
        active_rows = {}
        if active:
            active_rows = dict(
                ChokepointEntry.objects.filter(snapshot=active).values_list("entry_key", "source_hash")
            )

        staged_keys = set(staged_rows.keys())
        active_keys = set(active_rows.keys())

        added = len(staged_keys - active_keys)
        removed = len(active_keys - staged_keys)
        shared = staged_keys & active_keys
        changed = sum(1 for key in shared if staged_rows.get(key) != active_rows.get(key))
        unchanged = len(shared) - changed

        return ChokepointDiffSummaryType(
            snapshot_id=staged.id,
            active_snapshot_id=active.id if active else None,
            added=added,
            changed=changed,
            removed=removed,
            unchanged=unchanged,
            staged_count=len(staged_rows),
            active_count=len(active_rows),
        )

    def resolve_enrich_analytic_data(self, info, strategy_url, analytic_id):
        cache_key = f"mitre:text:{strategy_url}#{analytic_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        result = scrape_mitre_analytic_details(strategy_url, analytic_id)
        cache.set(cache_key, result, timeout=3600)
        return result

    def resolve_enrich_analytic_json(self, info, strategy_url, analytic_id):
        cache_key = f"mitre:json:{strategy_url}#{analytic_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        rows = scrape_mitre_log_sources_json(strategy_url, analytic_id)
        cache.set(cache_key, rows, timeout=3600)
        return rows

    def resolve_attack_navigator_layer(self, info):
        """
        Generates a MITRE ATT&CK Navigator JSON layer based on DEPLOYED PlaybookGraphs.
        Only active (non-revoked, non-deprecated) techniques are included.
        """
        playbooks = PlaybookGraph.objects.filter(
            status='DEPLOYED',
            mitre_technique__isnull=False,
            mitre_technique__revoked=False,
            mitre_technique__deprecated=False,
        ).select_related('mitre_technique')

        techniques_list = []
        for pb in playbooks:
            tech = pb.mitre_technique
            if not tech:
                continue

            score = pb.robustness_level if getattr(pb, 'robustness_level', 0) > 0 else 1

            technique_obj = {
                "techniqueID": tech.technique_id,
                "score": score,
                "color": "",
                "comment": f"Playbook: {getattr(pb, 'title', '')} (ID: {getattr(pb, 'custom_id', None) or pb.id})",
                "enabled": True,
                "metadata": [
                    {"name": "Status", "value": "Deployed"},
                    {"name": "Robustness", "value": str(score)},
                ],
            }
            techniques_list.append(technique_obj)

        # Look up the loaded ATT&CK version for the description field
        try:
            from platform_data.models import PlatformDataVersion
            ver_obj = PlatformDataVersion.objects.filter(framework='enterprise-attack').first()
            attack_version = f"v{ver_obj.version}" if ver_obj else "unknown"
        except Exception:
            attack_version = "unknown"

        layer_json = {
            "name": "HEFAISTOS Coverage Map",
            "version": "4.5",
            "domain": "enterprise-attack",
            "description": (
                f"Auto-generated coverage from HEFAISTOS Deployed Playbooks "
                f"(ATT&CK {attack_version})."
            ),
            "filters": {
                "platforms": [
                    "Windows", "Linux", "macOS",
                    "Azure AD", "Office 365", "SaaS",
                    "Network", "Containers",
                    "Google Workspace", "IaaS",
                    "PRE",
                ]
            },
            "sorting": 3,
            "layout": {
                "layout": "side",
                "aggregateFunction": "max",
                "showID": False,
                "showName": True,
            },
            "hideDisabled": False,
            "techniques": techniques_list,
            "gradient": {
                "colors": ["#ff6666", "#ffe766", "#8ec843", "#228b22"],
                "minValue": 1,
                "maxValue": 5,
            },
            "legendItems": [
                {"label": "Level 1-2 (Weak/Ephemeral)", "color": "#ff6666"},
                {"label": "Level 3 (LOLBin)", "color": "#ffe766"},
                {"label": "Level 4 (Behavioral)", "color": "#8ec843"},
                {"label": "Level 5 (Invariant)", "color": "#228b22"},
            ],
        }

        return json.dumps(layer_json)
    
    def resolve_all_d3fend_techniques(self, info, search=None, tactic=None, limit=None, offset=None):
        """List/search D3FEND techniques with optional filters"""
        queryset = D3fendDefensiveTechnique.objects.all()
        
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) |
                models.Q(d3fend_id__icontains=search) |
                models.Q(definition__icontains=search)
            )
        
        if tactic:
            queryset = queryset.filter(tactic__iexact=tactic)
        
        # Apply offset and limit using proper slicing
        if offset is not None and limit is not None:
            queryset = queryset[offset:offset + limit]
        elif offset is not None:
            queryset = queryset[offset:]
        elif limit is not None:
            queryset = queryset[:limit]
        
        return queryset
    
    def resolve_d3fend_technique(self, info, id):
        """Get single D3FEND technique by ID"""
        try:
            return D3fendDefensiveTechnique.objects.get(pk=id)
        except D3fendDefensiveTechnique.DoesNotExist:
            return None
    
    def resolve_d3fend_gap_analysis(self, info, attack_technique_id):
        """Analyze D3FEND coverage gaps for an ATT&CK technique"""
        # Find the ATT&CK technique
        try:
            attack_technique = MitreAttackTechnique.objects.get(technique_id=attack_technique_id)
        except MitreAttackTechnique.DoesNotExist:
            return None
        
        # Get recommended D3FEND countermeasures
        mappings = D3fendAttackMapping.objects.filter(attack_technique=attack_technique)
        recommended = [m.d3fend_technique for m in mappings]
        
        # Get current coverage from deployed playbooks
        deployed_playbooks = PlaybookGraph.objects.filter(
            status='DEPLOYED',
            mitre_technique=attack_technique
        ).prefetch_related('d3fend_techniques')
        
        current_coverage = set()
        for pb in deployed_playbooks:
            current_coverage.update(pb.d3fend_techniques.all())
        
        # Calculate gaps (recommended but not covered)
        gaps = [tech for tech in recommended if tech not in current_coverage]
        
        # Calculate coverage percentage
        coverage_percentage = 0.0
        if recommended:
            coverage_percentage = (len(current_coverage) / len(recommended)) * 100
        
        return D3fendGapAnalysisType(
            attack_technique=attack_technique,
            recommended_countermeasures=recommended,
            current_coverage=list(current_coverage),
            gaps=gaps,
            coverage_percentage=coverage_percentage
        )
    
    def resolve_d3fend_coverage_matrix(self, info):
        """Get full D3FEND coverage matrix organized by tactic"""
        # Get deployed playbooks with D3FEND techniques
        deployed_playbooks = PlaybookGraph.objects.filter(
            status='DEPLOYED'
        ).prefetch_related('d3fend_techniques')
        
        # Build set of covered technique IDs
        covered_technique_ids = set()
        technique_to_playbooks = {}
        
        for pb in deployed_playbooks:
            for tech in pb.d3fend_techniques.all():
                covered_technique_ids.add(tech.id)
                if tech.id not in technique_to_playbooks:
                    technique_to_playbooks[tech.id] = []
                technique_to_playbooks[tech.id].append(pb.title)
        
        # Group all D3FEND techniques by tactic
        tactics = ['Detect', 'Harden', 'Isolate', 'Deceive', 'Evict', 'Model']
        matrix = []
        
        for tactic in tactics:
            techniques = D3fendDefensiveTechnique.objects.filter(tactic=tactic)
            
            coverage_techniques = []
            for tech in techniques:
                is_covered = tech.id in covered_technique_ids
                implementing_playbooks = technique_to_playbooks.get(tech.id, [])
                
                coverage_techniques.append(
                    D3fendCoverageTechniqueType(
                        technique=tech,
                        is_covered=is_covered,
                        implementing_playbooks=implementing_playbooks
                    )
                )
            
            matrix.append(
                D3fendCoverageMatrixType(
                    tactic=tactic,
                    techniques=coverage_techniques
                )
            )

        return matrix

    def resolve_sharetide_index_entries(self, info, category=None):
        qs = ShareTideIndexEntry.objects.all()
        if category:
            qs = qs.filter(category=category)
        return qs


# --- MUTATIONS ---

class RunMitreImport(graphene.Mutation):
    """
    Admin-only mutation to trigger an async MITRE ATT&CK import job.
    Returns the newly created job immediately; poll `mitreImportJob(id)` for updates.
    """

    class Arguments:
        version = graphene.String(required=True, description="ATT&CK version string, e.g. '19.1'")
        mode = graphene.String(default_value="remote", description="'remote' or 'local'")

    job = graphene.Field(MitreImportJobType)

    @staticmethod
    def mutate(root, info, version, mode="remote"):
        from .tasks import run_mitre_import_job

        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")
        if not user.is_superuser:
            raise GraphQLError("Permission denied. Superuser access required.")

        version = str(version).lstrip("v").strip()
        mode_upper = mode.upper()
        if mode_upper not in (MitreImportJob.Mode.REMOTE, MitreImportJob.Mode.LOCAL):
            mode_upper = MitreImportJob.Mode.REMOTE

        job = MitreImportJob.objects.create(
            version=version,
            mode=mode_upper,
            status=MitreImportJob.Status.PENDING,
            triggered_by=user,
        )
        run_mitre_import_job(str(job.id))
        return RunMitreImport(job=job)


class RunChokepointImport(graphene.Mutation):
    """
    Admin-only mutation to trigger an async detection-chokepoints import job.
    """

    class Arguments:
        source_repo = graphene.String(
            default_value=DEFAULT_CHOKEPOINTS_REPO,
            description="Source repository URL.",
        )
        ref = graphene.String(
            default_value=DEFAULT_CHOKEPOINTS_REF,
            description="Source git ref (branch/tag/commit).",
        )
        mode = graphene.String(default_value="remote", description="'remote' or 'local'")

    job = graphene.Field(ChokepointImportJobType)

    @staticmethod
    def mutate(root, info, source_repo=DEFAULT_CHOKEPOINTS_REPO, ref=DEFAULT_CHOKEPOINTS_REF, mode="remote"):
        from .tasks import run_chokepoint_import_job

        user = _require_superuser(info)
        mode_upper = str(mode).upper().strip()
        if mode_upper not in (ChokepointImportJob.Mode.REMOTE, ChokepointImportJob.Mode.LOCAL):
            mode_upper = ChokepointImportJob.Mode.REMOTE

        source_ref = normalize_git_ref(ref)
        job = ChokepointImportJob.objects.create(
            source_repo=(source_repo or DEFAULT_CHOKEPOINTS_REPO).strip(),
            source_ref=source_ref,
            mode=mode_upper,
            status=ChokepointImportJob.Status.PENDING,
            triggered_by=user,
        )
        run_chokepoint_import_job(str(job.id))
        return RunChokepointImport(job=job)


class PromoteChokepointSnapshot(graphene.Mutation):
    """
    Promote a staged snapshot to active.
    """

    class Arguments:
        snapshot_id = graphene.UUID(required=True)

    success = graphene.Boolean()
    message = graphene.String()
    snapshot = graphene.Field(ChokepointSnapshotType)

    @staticmethod
    def mutate(root, info, snapshot_id):
        _require_superuser(info)
        try:
            snapshot = ChokepointSnapshot.objects.get(id=snapshot_id)
        except ChokepointSnapshot.DoesNotExist:
            raise GraphQLError("Chokepoint snapshot not found.")

        if snapshot.status == ChokepointSnapshot.Status.FAILED:
            raise GraphQLError("Cannot promote a failed snapshot.")

        _activate_chokepoint_snapshot(snapshot)
        return PromoteChokepointSnapshot(
            success=True,
            message=f"Snapshot {snapshot.id} is now active.",
            snapshot=snapshot,
        )


class RollbackChokepointSnapshot(graphene.Mutation):
    """
    Roll back active chokepoints to a selected snapshot.
    """

    class Arguments:
        snapshot_id = graphene.UUID(required=True)

    success = graphene.Boolean()
    message = graphene.String()
    snapshot = graphene.Field(ChokepointSnapshotType)

    @staticmethod
    def mutate(root, info, snapshot_id):
        _require_superuser(info)
        try:
            snapshot = ChokepointSnapshot.objects.get(id=snapshot_id)
        except ChokepointSnapshot.DoesNotExist:
            raise GraphQLError("Target snapshot not found.")

        if snapshot.status == ChokepointSnapshot.Status.FAILED:
            raise GraphQLError("Cannot roll back to a failed snapshot.")

        _activate_chokepoint_snapshot(snapshot)
        return RollbackChokepointSnapshot(
            success=True,
            message=f"Rolled back active chokepoints to snapshot {snapshot.id}.",
            snapshot=snapshot,
        )


class Mutation(graphene.ObjectType):
    run_mitre_import = RunMitreImport.Field(
        description="Trigger an async MITRE ATT&CK import (admin only)."
    )
    run_chokepoint_import = RunChokepointImport.Field(
        description="Trigger an async detection-chokepoints import (admin only)."
    )
    promote_chokepoint_snapshot = PromoteChokepointSnapshot.Field(
        description="Promote a staged chokepoint snapshot to active (admin only)."
    )
    rollback_chokepoint_snapshot = RollbackChokepointSnapshot.Field(
        description="Roll back to a selected chokepoint snapshot (admin only)."
    )
