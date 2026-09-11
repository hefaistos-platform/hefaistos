import graphene
from graphene import Scalar
import uuid
from graphql import GraphQLScalarType
import graphql_jwt
from django.contrib.auth.signals import user_logged_in
import identity.schema
import organizations.schema
import rules.schema
import playbooks.schema
import tags.schema
import review.schema
import notifications.schema
import data_catalog.schema
import knowledge.schema # Import the new knowledge schema
import ai_assistant.schema
import platform_data.schema
import log_catalog.schema # Import log_catalog schema
import news.schema # Import the news schema
import ach.schema # Import the ach schema
import advops.schema
import pain_points.schema  # Import the pain_points schema
import waiting_room.schema
import mgmt_reports.schema
from django.conf import settings
from identity.decorators import role_required, Roles

# Composite type for profile summary (defined before Query to avoid NameError)
class MyProfileSummary(graphene.ObjectType):
    workbenches = graphene.List(playbooks.schema.PlaybookType)
    ach_analyses = graphene.List(ach.schema.ACHAnalysisType)

# --- Minimal Git Config/Repository schema stubs (to enable RBAC wiring) ---
class GitConfigType(graphene.ObjectType):
    defaultRemote = graphene.String()
    branch = graphene.String()
    autoPullIntervalHours = graphene.Int()

class GetGitConfig(graphene.ObjectType):
    git_config = graphene.Field(GitConfigType)

    def resolve_git_config(self, info):
        # Placeholder: return defaults; replace with DB-backed settings
        return GitConfigType(defaultRemote="origin", branch="main", autoPullIntervalHours=12)


class UpdateGitConfig(graphene.Mutation):
    class Arguments:
        default_remote = graphene.String()
        branch = graphene.String()
        auto_pull_interval_hours = graphene.Int()

    ok = graphene.Boolean()
    config = graphene.Field(GitConfigType)

    @staticmethod
    @role_required([Roles.ADMIN, Roles.REVIEWER])
    def mutate(root, info, **kwargs):
        # Placeholder: accept values and echo back; persist later to SystemSettings/GitConfig
        cfg = GitConfigType(
            defaultRemote=kwargs.get('default_remote') or 'origin',
            branch=kwargs.get('branch') or 'main',
            autoPullIntervalHours=kwargs.get('auto_pull_interval_hours') or 12,
        )
        return UpdateGitConfig(ok=True, config=cfg)


class UUID(Scalar):
    """UUID scalar type for GraphQL."""
    
    @staticmethod
    def serialize(value):
        """Convert UUID object to string."""
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, str):
            return value
        return str(value)
    
    @staticmethod
    def parse_value(value):
        """Convert incoming value to UUID."""
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (ValueError, TypeError):
            raise ValueError(f"Invalid UUID: {value}")
    
    @staticmethod
    def parse_literal(ast):
        """Parse literal value from query."""
        if hasattr(ast, 'value'):
            try:
                return uuid.UUID(ast.value)
            except (ValueError, TypeError):
                return None
        return None


class Query(
    platform_data.schema.Query,
    ach.schema.Query, # Add ach queries
    advops.schema.Query,
    pain_points.schema.Query,  # Add pain_points queries
    waiting_room.schema.Query,
    mgmt_reports.schema.Query,
    knowledge.schema.Query, # Add this
    news.schema.Query,  # Add news queries
    GetGitConfig,
    ai_assistant.schema.Query,
    notifications.schema.Query,
    review.schema.Query,
    data_catalog.schema.Query,
    log_catalog.schema.Query, # Add log_catalog queries
    playbooks.schema.Query,
    tags.schema.Query,
    rules.schema.Query,
    organizations.schema.Query,
    identity.schema.Query,
    graphene.ObjectType
):
    """
    HEFAISTOS GraphQL API
    (c) 2025-2026 Jan Pohl - m3c4n1sm0 and multiple AI bots
    
    Detection Engineering Platform
    """
    version = graphene.String()
    copyright = graphene.String()

    # Composite summary for profile page
    my_profile_summary = graphene.Field(MyProfileSummary)

    def resolve_version(self, info):
        return getattr(settings, 'HEFAISTOS_VERSION', '1.0')

    def resolve_copyright(self, info):
        return getattr(settings, 'HEFAISTOS_COPYRIGHT', '')

    def resolve_my_profile_summary(self, info):
        user = info.context.user
        if user.is_anonymous:
            return None
        from playbooks.models import DetectionPlaybook
        from ach.models import ACHAnalysis
        # Workbenches: user's authored playbooks, recent first
        workbenches = list(
            DetectionPlaybook.objects.filter(author=user).order_by('-updated_at')[:24]
        )
        # ACH Analyses: owned by user, recent first
        ach_analyses = list(
            ACHAnalysis.objects.filter(owner=user).order_by('-updated_at')[:24]
        )
        return MyProfileSummary(workbenches=workbenches, ach_analyses=ach_analyses)


class ObtainJSONWebTokenWithSignal(graphql_jwt.ObtainJSONWebToken):
    """
    Custom JWT mutation that fires the user_logged_in signal
    to ensure last_login is updated on every login.
    """
    @classmethod
    def resolve(cls, root, info, **kwargs):
        # Call the parent resolve to handle authentication
        result = super().resolve(root, info, **kwargs)
        
        # If authentication was successful and we have a user in context
        if hasattr(info.context, 'user') and info.context.user and info.context.user.is_authenticated:
            # Fire the user_logged_in signal
            user_logged_in.send(
                sender=info.context.user.__class__,
                request=info.context,
                user=info.context.user
            )
        
        return result


class Mutation(
    ach.schema.Mutation, # Add ach mutations
    advops.schema.Mutation,
    pain_points.schema.Mutation,  # Add pain_points mutations
    waiting_room.schema.Mutation,
    mgmt_reports.schema.Mutation,
    identity.schema.Mutation,
    knowledge.schema.Mutation, # Add this
    news.schema.Mutation,  # Add news mutations
    ai_assistant.schema.Mutation,
    notifications.schema.Mutation,
    data_catalog.schema.Mutation,
    log_catalog.schema.Mutation, # Add log_catalog mutations
    review.schema.Mutation,
    playbooks.schema.Mutation,
    rules.schema.Mutation,  # <-- Added to expose rule repository mutations (create/update/delete)
    tags.schema.Mutation,
    organizations.schema.Mutation,  # Organization CRUD for superusers
    platform_data.schema.Mutation,  # MITRE import jobs
    graphene.ObjectType
):
    token_auth = ObtainJSONWebTokenWithSignal.Field()
    verify_token = graphql_jwt.Verify.Field()
    refresh_token = graphql_jwt.Refresh.Field()

    # Git/Repository operations (RBAC gated)
    update_git_config = UpdateGitConfig.Field()

# Be explicit about camelCase field names in the GraphQL schema
schema = graphene.Schema(query=Query, mutation=Mutation, auto_camelcase=True)
# Make sure schema includes the UUID scalar
schema = graphene.Schema(
    query=Query,
    mutation=Mutation,
    types=[UUID]  # Add this to register the scalar
)
