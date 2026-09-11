import graphene
from graphene_django import DjangoObjectType
from graphql import GraphQLError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
import logging
import re
from .models import ADVOPSReport
from .misp_integration import MISPClient, MISPIntegrationError, parse_infrastructure_summary, extract_mitre_techniques
from organizations.models import MISPInstance
from identity.decorators import is_bot_auditor_user
from mgmt_reports.cache_utils import invalidate_mgmt_cave_stats_cache

logger = logging.getLogger(__name__)

# Hunt ID format pattern for parsing
HUNT_ID_PATTERN = r'ADV-\d{4}-\d{2}-(\d+)'


def generate_next_hunt_id(organization):
    """
    Generate the next hunt ID in format ADV-YYYY-MM-XXX where XXX is consecutive.
    Returns a unique hunt ID for the given organization.
    """
    now = timezone.now()
    year = now.year
    month = f'{now.month:02d}'
    prefix = f"ADV-{year}-{month}-"
    
    # Find all hunt IDs matching this month's prefix for this organization
    existing_hunts = ADVOPSReport.objects.filter(
        organization=organization,
        hunt_id__startswith=prefix
    ).values_list('hunt_id', flat=True)
    
    # Extract numbers from matching hunt IDs
    max_number = 0
    for hunt_id in existing_hunts:
        match = re.search(HUNT_ID_PATTERN, hunt_id)
        if match:
            num = int(match.group(1))
            if num > max_number:
                max_number = num
    
    # Generate next number (zero-padded to 3 digits)
    next_number = max_number + 1
    hunt_id = f"{prefix}{next_number:03d}"
    
    return hunt_id


class ADVOPSReportType(DjangoObjectType):
    class Meta:
        model = ADVOPSReport
        fields = (
            "id",
            "hunt_id",
            "hypothesis",
            "status",
            "priority",
            "author",
            "organization",
            "allow_remote_pull",
            "created_at",
            "updated_at",
            "verification_summary",
            "infrastructure_summary",
            "pivot_summary",
            "false_positive_summary",
            "mitre_summary",
            "detection_logic_summary",
        )


class ADVOPSReportInput(graphene.InputObjectType):
    # hunt_id is optional for updates (Kanban drag) but validated on create
    hunt_id = graphene.String(required=False)
    hypothesis = graphene.String()
    status = graphene.String()
    priority = graphene.String()
    verification_summary = graphene.String()
    infrastructure_summary = graphene.String()
    pivot_summary = graphene.String()
    false_positive_summary = graphene.String()
    mitre_summary = graphene.String()
    detection_logic_summary = graphene.String()


class Query(graphene.ObjectType):
    all_advops_reports = graphene.List(ADVOPSReportType)
    advops_report = graphene.Field(ADVOPSReportType, id=graphene.UUID(required=True))
    next_hunt_id = graphene.String(description="Generate the next available hunt ID in format ADV-YYYY-MM-XXX")

    def resolve_all_advops_reports(self, info):
        user = info.context.user
        if user.is_anonymous:
            return []
        if is_bot_auditor_user(user):
            return ADVOPSReport.objects.all().order_by("-updated_at")
        return ADVOPSReport.objects.filter(organization=user.organization).order_by("-updated_at")

    def resolve_advops_report(self, info, id):
        user = info.context.user
        if user.is_anonymous:
            return None
        try:
            if is_bot_auditor_user(user):
                return ADVOPSReport.objects.get(id=id)
            return ADVOPSReport.objects.get(id=id, organization=user.organization)
        except ADVOPSReport.DoesNotExist:
            return None

    def resolve_next_hunt_id(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")
        return generate_next_hunt_id(user.organization)


class CreateADVOPSReport(graphene.Mutation):
    class Arguments:
        input = ADVOPSReportInput(required=True)

    report = graphene.Field(ADVOPSReportType)

    @classmethod
    @transaction.atomic
    def mutate(cls, root, info, input):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")
        
        # Auto-generate hunt_id if not provided
        hunt_id = input.hunt_id
        if not hunt_id:
            hunt_id = generate_next_hunt_id(user.organization)
            logger.info(f"Auto-generated hunt ID: {hunt_id}")
        
        report = ADVOPSReport.objects.create(
            hunt_id=hunt_id,
            hypothesis=input.hypothesis or "",
            status=input.status or ADVOPSReport.Status.IDEA,
            priority=input.priority or ADVOPSReport.Priority.MEDIUM,
            verification_summary=input.verification_summary or "",
            infrastructure_summary=input.infrastructure_summary or "",
            pivot_summary=input.pivot_summary or "",
            false_positive_summary=input.false_positive_summary or "",
            mitre_summary=input.mitre_summary or "",
            detection_logic_summary=input.detection_logic_summary or "",
            author=user,
            organization=user.organization,
        )
        invalidate_mgmt_cave_stats_cache(getattr(user.organization, 'id', None))
        return CreateADVOPSReport(report=report)


class UpdateADVOPSReport(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)
        input = ADVOPSReportInput(required=True)

    report = graphene.Field(ADVOPSReportType)

    @classmethod
    @transaction.atomic
    def mutate(cls, root, info, id, input):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")
        try:
            report = ADVOPSReport.objects.get(id=id, organization=user.organization)
        except ADVOPSReport.DoesNotExist:
            raise GraphQLError("Not found")

        for field in [
            "hunt_id",
            "hypothesis",
            "status",
            "priority",
            "verification_summary",
            "infrastructure_summary",
            "pivot_summary",
            "false_positive_summary",
            "mitre_summary",
            "detection_logic_summary",
        ]:
            value = getattr(input, field, None)
            if value is not None:
                setattr(report, field, value)
        report.save()
        invalidate_mgmt_cave_stats_cache(getattr(user.organization, 'id', None))
        return UpdateADVOPSReport(report=report)


class DeleteADVOPSReport(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)

    ok = graphene.Boolean()

    @classmethod
    @transaction.atomic
    def mutate(cls, root, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")
        try:
            report_filters = {"id": id}
            if not user.is_superuser:
                report_filters["organization"] = user.organization
            report = ADVOPSReport.objects.get(**report_filters)
        except ADVOPSReport.DoesNotExist:
            raise GraphQLError("Not found")
        org_id = getattr(report.organization, 'id', None)
        report.delete()
        invalidate_mgmt_cave_stats_cache(org_id)
        return DeleteADVOPSReport(ok=True)


class PushADVOPSReportToMISP(graphene.Mutation):
    """Push an ADVOPS report to MISP as a new event."""
    
    class Arguments:
        id = graphene.UUID(required=True)
        misp_instance_id = graphene.UUID(required=False, description="ID of the MISPInstance to push to. Required when the organization has multiple instances.")

    success = graphene.Boolean()
    message = graphene.String()
    event_id = graphene.Int()

    @classmethod
    @transaction.atomic
    def mutate(cls, root, info, id, misp_instance_id=None):
        user = info.context.user
        logger.info(f"PushADVOPSReportToMISP called by user: {user}")
        
        if user.is_anonymous:
            raise GraphQLError("Authentication required")
        
        try:
            report = ADVOPSReport.objects.get(id=id, organization=user.organization)
            logger.info(f"Found ADVOPS report: {report.hunt_id}")
        except ADVOPSReport.DoesNotExist:
            logger.error(f"ADVOPS report not found: {id}")
            raise GraphQLError("Report not found")

        try:
            # Resolve MISP instance credentials
            misp_url = None
            misp_auth_key = None
            misp_verify_ssl = None

            org_instances = MISPInstance.objects.filter(organization=user.organization)
            if org_instances.exists():
                # Per-organization MISP instances are configured
                if misp_instance_id:
                    try:
                        instance = org_instances.get(pk=misp_instance_id)
                    except MISPInstance.DoesNotExist:
                        raise GraphQLError("MISP instance not found for this organization.")
                elif org_instances.count() == 1:
                    instance = org_instances.first()
                else:
                    raise GraphQLError(
                        "Multiple MISP instances are configured. Please specify misp_instance_id."
                    )
                misp_url = instance.url
                misp_auth_key = instance.auth_key
                misp_verify_ssl = instance.verify_ssl
                logger.info(f"Using org MISP instance: {instance.name} ({misp_url})")
            else:
                logger.info("No org-level MISP instances found; falling back to global settings.")

            # Initialize MISP client
            logger.info("Initializing MISP client")
            try:
                misp_client = MISPClient(url=misp_url, auth_key=misp_auth_key, verify_ssl=misp_verify_ssl)
            except MISPIntegrationError as e:
                error_msg = str(e)
                logger.error(f"MISP client init failed: {error_msg}", exc_info=True)
                if "not configured" in error_msg:
                    raise GraphQLError("MISP is not configured. Add a MISP instance in the Repositories settings or set MISP_URL and MISP_API_KEY.")
                elif "incomplete" in error_msg:
                    raise GraphQLError("MISP configuration is incomplete. Please check your MISP settings.")
                else:
                    raise GraphQLError(f"MISP configuration error: {error_msg}")

            # Build event name from Hunt ID + Hypothesis
            event_name = f"{report.hunt_id}: {report.hypothesis}"[:255]  # MISP limit
            logger.info(f"Creating MISP event with name: {event_name}")

            # Parse infrastructure summary to extract attributes
            attributes = parse_infrastructure_summary(report.infrastructure_summary)
            logger.info(f"Parsed {len(attributes)} attributes from infrastructure summary")

            # Extract MITRE techniques from MITRE mapping
            mitre_techniques = extract_mitre_techniques(report.mitre_summary)
            logger.info(f"Extracted {len(mitre_techniques)} MITRE techniques")

            # Push to MISP
            logger.info("Pushing to MISP...")
            try:
                result = misp_client.create_event(
                    event_name=event_name,
                    mitre_patterns=mitre_techniques,
                    attributes=attributes,
                    pivot_summary=report.pivot_summary,
                    verification_summary=report.verification_summary,
                    false_positive_analysis=report.false_positive_summary,
                )
            except MISPIntegrationError as e:
                error_text = str(e).lower()
                logger.error(f"MISP create_event failed: {str(e)}", exc_info=True)
                # Provide user-friendly error messages
                if "302" in str(e) or "login" in error_text or "unauthorized" in error_text:
                    raise GraphQLError("MISP authentication failed. The API key is invalid or the user lacks API permissions. Please verify your MISP_API_KEY in the admin panel and ensure the user has API access enabled.")
                elif "connection" in error_text or "timeout" in error_text:
                    raise GraphQLError(f"Cannot connect to MISP server. Verify MISP is running and accessible at the configured URL.")
                elif "html" in error_text or "error page" in error_text:
                    raise GraphQLError("MISP returned an error page. This usually indicates authentication failure. Check your API key.")
                else:
                    raise GraphQLError(f"MISP API error: {str(e)}")
            
            logger.info(f"MISP push successful: {result}")

            return PushADVOPSReportToMISP(
                success=True,
                message=result.get('message', 'Event created successfully'),
                event_id=result.get('event_id'),
            )
        except MISPIntegrationError as e:
            logger.error(f"MISP integration error: {str(e)}", exc_info=True)
            raise GraphQLError(f"MISP integration error: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to push to MISP: {str(e)}", exc_info=True)
            raise GraphQLError(f"Failed to push to MISP: {str(e)}")


class SetADVOPSRemotePull(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)
        enabled = graphene.Boolean(required=True)

    success = graphene.Boolean()
    message = graphene.String()
    report = graphene.Field(ADVOPSReportType)

    @classmethod
    @transaction.atomic
    def mutate(cls, root, info, id, enabled):
        user = info.context.user
        if user.is_anonymous:
            raise GraphQLError("Authentication required")

        try:
            report = ADVOPSReport.objects.get(id=id, organization=user.organization)
        except ADVOPSReport.DoesNotExist:
            raise GraphQLError("Not found")

        is_admin = bool(
            getattr(user, 'role', None) == 'ADMIN'
            or getattr(user, 'is_superuser', False)
            or getattr(user, 'is_staff', False)
        )
        if report.author_id != getattr(user, 'id', None) and not is_admin:
            raise GraphQLError("Only author or admin can change remote pull access")

        report.allow_remote_pull = bool(enabled)
        report.save(update_fields=['allow_remote_pull', 'updated_at'])
        return SetADVOPSRemotePull(
            success=True,
            message='Remote pull enabled for this ADVOPS hunt' if report.allow_remote_pull else 'Remote pull disabled for this ADVOPS hunt',
            report=report,
        )


class Mutation(graphene.ObjectType):
    create_advops_report = CreateADVOPSReport.Field()
    update_advops_report = UpdateADVOPSReport.Field()
    delete_advops_report = DeleteADVOPSReport.Field()
    push_advops_report_to_misp = PushADVOPSReportToMISP.Field()
    set_advops_remote_pull = SetADVOPSRemotePull.Field()
