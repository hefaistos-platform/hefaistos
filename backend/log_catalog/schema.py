import graphene
from graphene_django import DjangoObjectType
from .models import LogSource
from platform_data.models import MitreDataComponent
from identity.decorators import Roles
from core.mcs_logging import search_security_logs

class LogSourceType(DjangoObjectType):
    class Meta:
        model = LogSource
        fields = "__all__"

class CreateLogSource(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        mitre_component_id = graphene.String() # STIX ID or DB ID
        mitre_log_provider = graphene.String()
        mitre_channel = graphene.String()
        index_pattern = graphene.String()

    log_source = graphene.Field(LogSourceType)

    def mutate(self, info, name, **kwargs):
        # 1. Resolve Component if ID provided
        comp = None
        if 'mitre_component_id' in kwargs:
            cid = kwargs.pop('mitre_component_id')
            # Try finding by DB ID first, then STIX ID
            try:
                comp = MitreDataComponent.objects.get(pk=cid)
            except:
                comp = MitreDataComponent.objects.filter(stix_id=cid).first()

        # 2. Create
        source = LogSource.objects.create(
            name=name,
            mitre_component=comp,
            **kwargs
        )
        return CreateLogSource(log_source=source)

class Mutation(graphene.ObjectType):
    create_log_source = CreateLogSource.Field()


class MCSSecurityLogType(graphene.ObjectType):
    id = graphene.String()
    timestamp = graphene.String()
    level = graphene.String()
    logger = graphene.String()
    message = graphene.String()
    action = graphene.String()
    outcome = graphene.String()
    reason = graphene.String()
    event_code = graphene.String()
    user_id = graphene.String()
    user_name = graphene.String()
    source_ip = graphene.String()
    request_method = graphene.String()
    url_path = graphene.String()
    service_name = graphene.String()


class MCSSecurityLogSearchResultType(graphene.ObjectType):
    total = graphene.Int(required=True)
    logs = graphene.List(MCSSecurityLogType, required=True)


class Query(graphene.ObjectType):
    all_log_sources = graphene.List(LogSourceType)
    mcs_security_logs = graphene.Field(
        MCSSecurityLogSearchResultType,
        limit=graphene.Int(default_value=100),
        offset=graphene.Int(default_value=0),
        level=graphene.String(),
        action=graphene.String(),
        search=graphene.String(),
        user=graphene.String(),
        description="Returns centralized MCS security logs (last 72 hours only). Admin-only.",
    )

    def resolve_all_log_sources(self, info):
        return LogSource.objects.all()

    def resolve_mcs_security_logs(self, info, limit=100, offset=0, level=None, action=None, search=None, user=None):
        request_user = info.context.user
        if request_user.is_anonymous:
            raise Exception("Authentication required")

        role = (getattr(request_user, 'role', '') or '').upper()
        is_admin = role == Roles.ADMIN or bool(getattr(request_user, 'is_superuser', False) or getattr(request_user, 'is_staff', False))
        if not is_admin:
            raise Exception("Admin role required")

        try:
            result = search_security_logs(
                limit=limit,
                offset=offset,
                level=level,
                action=action,
                search=search,
                user=user,
            )
        except Exception as exc:
            raise Exception(f"Centralized log storage is currently unavailable: {exc}")

        return MCSSecurityLogSearchResultType(
            total=result.get('total', 0),
            logs=[
                MCSSecurityLogType(
                    id=item.get('id'),
                    timestamp=item.get('timestamp'),
                    level=item.get('level'),
                    logger=item.get('logger'),
                    message=item.get('message'),
                    action=item.get('action'),
                    outcome=item.get('outcome'),
                    reason=item.get('reason'),
                    event_code=item.get('event_code'),
                    user_id=item.get('user_id'),
                    user_name=item.get('user_name'),
                    source_ip=item.get('source_ip'),
                    request_method=item.get('request_method'),
                    url_path=item.get('url_path'),
                    service_name=item.get('service_name'),
                )
                for item in result.get('logs', [])
            ],
        )
