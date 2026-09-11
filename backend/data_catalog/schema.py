import graphene
from django.db import transaction
from graphene_django import DjangoObjectType
from.models import DataSource, DataSourceField, MitreDeepImportJob
from identity.decorators import role_required, Roles
from platform_data.models import MitreDataComponent, MitreDomain


def _normalize_text(value):
    return (value or "").strip()


def _guess_platform(*values):
    haystack = " ".join(_normalize_text(v).lower() for v in values if v)
    if not haystack:
        return None

    windows_markers = ("windows", "wineventlog", "sysmon", "etw", "powershell")
    linux_markers = ("linux", "auditd", "syslog", "journald", "systemd")
    mac_markers = ("mac", "darwin", "osquery", "endpointsecurity", "unified log")
    cloud_markers = ("azure", "m365", "office 365", "aws", "gcp", "cloudtrail")
    network_markers = ("network", "dns", "proxy", "firewall", "netflow")

    if any(marker in haystack for marker in windows_markers):
        return "Windows"
    if any(marker in haystack for marker in linux_markers):
        return "Linux"
    if any(marker in haystack for marker in mac_markers):
        return "macOS"
    if any(marker in haystack for marker in cloud_markers):
        return "Cloud"
    if any(marker in haystack for marker in network_markers):
        return "Network"
    return None


def _build_import_description(component):
    source_description = _normalize_text(getattr(component.data_source, 'description', ''))
    component_description = _normalize_text(component.description)

    lines = ["Imported from MITRE ATT&CK required data source catalog."]
    if component_description:
        lines.append(f"Data Component: {component_description}")
    if source_description:
        lines.append(f"MITRE Data Source: {source_description}")
    return "\n\n".join(lines)


def _require_admin_user(info):
    user = info.context.user
    if user.is_anonymous:
        raise Exception("Authentication credentials were not provided")
    if not (getattr(user, 'role', None) == Roles.ADMIN or getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)):
        raise Exception("Permission denied. ADMIN role required.")
    return user


class MitreDeepImportJobType(DjangoObjectType):
    progress_percent = graphene.Float(description="Completion percent (0-100)")
    duration_seconds = graphene.Float(description="Wall-clock duration in seconds, or null if not finished.")

    class Meta:
        model = MitreDeepImportJob
        fields = (
            "id",
            "organization",
            "include_revoked",
            "status",
            "total_analytics",
            "processed_analytics",
            "failed_analytics",
            "total_rows",
            "imported_rows",
            "created_count",
            "existing_count",
            "updated_count",
            "log",
            "error",
            "created_at",
            "updated_at",
            "started_at",
            "finished_at",
            "triggered_by",
        )

    def resolve_progress_percent(self, info):
        total = int(self.total_analytics or 0)
        processed = int(self.processed_analytics or 0)
        if total <= 0:
            return 100.0 if self.status == MitreDeepImportJob.Status.SUCCESS else 0.0
        return min(100.0, (processed / total) * 100.0)

    def resolve_duration_seconds(self, info):
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

class DataSourceFieldType(DjangoObjectType):
    class Meta:
        model = DataSourceField
        fields = "__all__"

class DataSourceType(DjangoObjectType):
    fields = graphene.List(DataSourceFieldType)

    class Meta:
        model = DataSource
        fields = "__all__"

    def resolve_fields(self, info):
        return self.fields.all()


class DataSourcePageType(graphene.ObjectType):
    items = graphene.List(DataSourceType, required=True)
    total_count = graphene.Int(required=True)

class Query(graphene.ObjectType):
    all_data_sources = graphene.List(DataSourceType, description="Retrieves all data sources for the user's organization.")
    data_source = graphene.Field(DataSourceType, id=graphene.ID(required=True), description="Retrieves a single data source by its ID.")
    data_sources_page = graphene.Field(
        DataSourcePageType,
        query=graphene.String(),
        platform=graphene.String(),
        limit=graphene.Int(default_value=60),
        offset=graphene.Int(default_value=0),
        description="Paginated data source list for the user's organization with optional search/platform filtering.",
    )
    data_source_platforms = graphene.List(
        graphene.String,
        description="Distinct data source platform values for the user's organization.",
    )
    mitre_deep_import_job = graphene.Field(
        MitreDeepImportJobType,
        id=graphene.UUID(required=True),
        description="Get a single MITRE deep import job for the current organization (ADMIN only).",
    )
    mitre_deep_import_jobs = graphene.List(
        MitreDeepImportJobType,
        limit=graphene.Int(default_value=20),
        description="List recent MITRE deep import jobs for the current organization (ADMIN only).",
    )
    search_data_sources = graphene.List(
        DataSourceType,
        query=graphene.String(required=True),
        limit=graphene.Int(default_value=10),
        description="Search data sources by name or platform for autocomplete."
    )

    def resolve_all_data_sources(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        return DataSource.objects.filter(organization=user.organization)

    def resolve_data_source(self, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        # Security Check: Filter by both ID and the user's organization
        return DataSource.objects.filter(pk=id, organization=user.organization).first()

    def resolve_search_data_sources(self, info, query, limit=10):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        
        from django.db.models import Q
        
        # Search by name or platform (case-insensitive)
        qs = DataSource.objects.filter(
            organization=user.organization
        ).filter(
            Q(name__icontains=query) | Q(platform__icontains=query) | Q(description__icontains=query)
        )[:limit]
        
        return qs

    def resolve_data_sources_page(self, info, query=None, platform=None, limit=60, offset=0):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        from django.db.models import Q

        bounded_limit = max(1, min(int(limit or 60), 200))
        bounded_offset = max(0, int(offset or 0))

        qs = DataSource.objects.filter(organization=user.organization)

        search_term = _normalize_text(query)
        if search_term:
            qs = qs.filter(
                Q(name__icontains=search_term)
                | Q(platform__icontains=search_term)
                | Q(description__icontains=search_term)
            )

        platform_term = _normalize_text(platform)
        if platform_term and platform_term.upper() != 'ALL':
            qs = qs.filter(platform=platform_term)

        qs = qs.order_by('-updated_at', '-id')
        total_count = qs.count()
        items = list(qs[bounded_offset: bounded_offset + bounded_limit])
        return DataSourcePageType(items=items, total_count=total_count)

    def resolve_data_source_platforms(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        values = (
            DataSource.objects.filter(organization=user.organization)
            .exclude(platform__isnull=True)
            .exclude(platform__exact='')
            .values_list('platform', flat=True)
            .distinct()
            .order_by('platform')
        )
        return list(values)

    def resolve_mitre_deep_import_job(self, info, id):
        user = _require_admin_user(info)
        return MitreDeepImportJob.objects.filter(id=id, organization=user.organization).first()

    def resolve_mitre_deep_import_jobs(self, info, limit=20):
        user = _require_admin_user(info)
        bounded_limit = max(1, min(limit or 20, 50))
        return MitreDeepImportJob.objects.filter(organization=user.organization)[:bounded_limit]

class CreateDataSource(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        platform = graphene.String()
        description = graphene.String()

    data_source = graphene.Field(DataSourceType)

    class Meta:
        description = "Creates a new data source for the user's organization."

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST, Roles.REVIEWER, Roles.VIEWER])
    def mutate(root, info, name, **kwargs):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        data_source = DataSource(name=name, organization=user.organization, **kwargs)
        data_source.save()
        return CreateDataSource(data_source=data_source)

class AddDataSourceField(graphene.Mutation):
    class Arguments:
        data_source_id = graphene.ID(required=True)
        field_name = graphene.String(required=True)
        data_type = graphene.String()
        description = graphene.String()
        example_value = graphene.String()

    data_source_field = graphene.Field(DataSourceFieldType)

    class Meta:
        description = "Adds a new field to an existing data source. The data source must belong to the user's organization."

    @staticmethod
    def mutate(root, info, data_source_id, field_name, **kwargs):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        # Security Check: Ensure the parent data source belongs to the user's org
        try:
            data_source = DataSource.objects.get(pk=data_source_id, organization=user.organization)
        except DataSource.DoesNotExist:
            raise Exception("Data source not found or you do not have permission")

        field = DataSourceField(data_source=data_source, field_name=field_name, **kwargs)
        field.save()
        return AddDataSourceField(data_source_field=field)


class ImportMitreRequiredDataSources(graphene.Mutation):
    class Arguments:
        include_revoked = graphene.Boolean(
            default_value=False,
            description="When true, includes MITRE components linked only to revoked/deprecated techniques.",
        )

    created_count = graphene.Int(required=True)
    existing_count = graphene.Int(required=True)
    updated_count = graphene.Int(required=True)
    total_candidates = graphene.Int(required=True)

    class Meta:
        description = "Bulk-import MITRE ATT&CK required data sources into the caller's Data Catalog."

    @staticmethod
    @role_required([Roles.ADMIN])
    @transaction.atomic
    def mutate(root, info, include_revoked=False):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        if not getattr(user, 'organization', None):
            raise Exception("Your account is not linked to an organization")

        components = MitreDataComponent.objects.filter(
            domain=MitreDomain.ENTERPRISE,
            data_source__isnull=False,
        )
        if not include_revoked:
            components = components.filter(
                techniques__revoked=False,
                techniques__deprecated=False,
            )

        components = (
            components
            .select_related('data_source')
            .order_by('data_source__name', 'name')
            .distinct()
        )

        existing_sources = {
            _normalize_text(ds.name).lower(): ds
            for ds in DataSource.objects.filter(organization=user.organization)
        }

        created_count = 0
        existing_count = 0
        updated_count = 0
        total_candidates = 0

        field_description = 'Imported from MITRE ATT&CK bulk data-source import'

        for component in components:
            source_name = _normalize_text(component.data_source.name if component.data_source else '')
            component_name = _normalize_text(component.name)
            if not source_name or not component_name:
                continue

            total_candidates += 1
            canonical_name = f"{source_name} - {component_name}"
            lookup_key = canonical_name.lower()
            guessed_platform = _guess_platform(source_name, component_name)
            import_description = _build_import_description(component)

            data_source = existing_sources.get(lookup_key)
            if data_source is None:
                data_source = DataSource.objects.create(
                    name=canonical_name,
                    organization=user.organization,
                    platform=guessed_platform,
                    description=import_description,
                )
                existing_sources[lookup_key] = data_source
                created_count += 1
            else:
                existing_count += 1
                touched = False
                if guessed_platform and not _normalize_text(data_source.platform):
                    data_source.platform = guessed_platform
                    touched = True
                if import_description and not _normalize_text(data_source.description):
                    data_source.description = import_description
                    touched = True
                if touched:
                    data_source.save()
                    updated_count += 1

            field_defaults = [
                {
                    'field_name': 'data_component',
                    'data_type': 'string',
                    'description': field_description,
                    'example_value': component_name,
                },
                {
                    'field_name': 'provider',
                    'data_type': 'string',
                    'description': field_description,
                    'example_value': source_name,
                },
                {
                    'field_name': 'channel',
                    'data_type': 'string',
                    'description': field_description,
                    'example_value': component_name,
                },
            ]

            for field_data in field_defaults:
                field_name = field_data.pop('field_name')
                DataSourceField.objects.get_or_create(
                    data_source=data_source,
                    field_name=field_name,
                    defaults=field_data,
                )

        return ImportMitreRequiredDataSources(
            created_count=created_count,
            existing_count=existing_count,
            updated_count=updated_count,
            total_candidates=total_candidates,
        )


class RunMitreDeepImport(graphene.Mutation):
    """
    Admin-only mutation to queue a deep MITRE required-data-source import job.
    """

    class Arguments:
        include_revoked = graphene.Boolean(
            default_value=False,
            description="When true, include rows linked only to revoked/deprecated ATT&CK techniques.",
        )

    job = graphene.Field(MitreDeepImportJobType)

    @staticmethod
    @role_required([Roles.ADMIN])
    def mutate(root, info, include_revoked=False):
        from .tasks import run_mitre_deep_import_job

        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        if not getattr(user, 'organization', None):
            raise Exception("Your account is not linked to an organization")

        running_job = MitreDeepImportJob.objects.filter(
            organization=user.organization,
            status__in=[MitreDeepImportJob.Status.PENDING, MitreDeepImportJob.Status.RUNNING],
        ).first()
        if running_job:
            return RunMitreDeepImport(job=running_job)

        job = MitreDeepImportJob.objects.create(
            organization=user.organization,
            include_revoked=bool(include_revoked),
            status=MitreDeepImportJob.Status.PENDING,
            triggered_by=user,
        )
        run_mitre_deep_import_job(str(job.id))
        return RunMitreDeepImport(job=job)

# --- New mutation classes for updating/deleting data sources and fields ---
class UpdateDataSource(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        name = graphene.String()
        platform = graphene.String()
        description = graphene.String()

    data_source = graphene.Field(DataSourceType)

    @staticmethod
    def mutate(root, info, id, **kwargs):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        try:
            data_source = DataSource.objects.get(pk=id, organization=user.organization)
        except DataSource.DoesNotExist:
            raise Exception("Data source not found or you do not have permission")

        for field, value in kwargs.items():
            setattr(data_source, field, value)

        data_source.save()
        return UpdateDataSource(data_source=data_source)


class DeleteDataSource(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    ok = graphene.Boolean()

    @staticmethod
    def mutate(root, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        try:
            data_source = DataSource.objects.get(pk=id, organization=user.organization)
        except DataSource.DoesNotExist:
            raise Exception("Data source not found or you do not have permission")

        data_source.delete()
        return DeleteDataSource(ok=True)


class UpdateDataSourceField(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        field_name = graphene.String()
        data_type = graphene.String()
        description = graphene.String()
        example_value = graphene.String()

    data_source_field = graphene.Field(DataSourceFieldType)

    @staticmethod
    def mutate(root, info, id, **kwargs):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        try:
            # Security Check: Ensure the field belongs to a data source in the user's org
            field = DataSourceField.objects.get(pk=id, data_source__organization=user.organization)
        except DataSourceField.DoesNotExist:
            raise Exception("Field not found or you do not have permission")

        for field_name, value in kwargs.items():
            setattr(field, field_name, value)

        field.save()
        return UpdateDataSourceField(data_source_field=field)


class DeleteDataSourceField(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    ok = graphene.Boolean()

    @staticmethod
    def mutate(root, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        try:
            field = DataSourceField.objects.get(pk=id, data_source__organization=user.organization)
        except DataSourceField.DoesNotExist:
            raise Exception("Field not found or you do not have permission")

        field.delete()
        return DeleteDataSourceField(ok=True)

class Mutation(graphene.ObjectType):
    create_data_source = CreateDataSource.Field()
    import_mitre_required_data_sources = ImportMitreRequiredDataSources.Field()
    run_mitre_deep_import = RunMitreDeepImport.Field()
    add_data_source_field = AddDataSourceField.Field()
    update_data_source = UpdateDataSource.Field()
    delete_data_source = DeleteDataSource.Field()
    update_data_source_field = UpdateDataSourceField.Field()
    delete_data_source_field = DeleteDataSourceField.Field()
