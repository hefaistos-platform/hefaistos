import graphene
from graphene_django import DjangoObjectType
from.models import TenantTag
from playbooks.models import PlaybookGraph, DetectionPlaybook
from organizations.schema import OrganizationType

class TagType(DjangoObjectType):
    # Explicitly expose the organization as a nested field to avoid
    # potential registration/order issues with automatic conversion.
    organization = graphene.Field(OrganizationType)
    usage_count = graphene.Int()

    def resolve_organization(self, info):
        return self.organization
    class Meta:
        model = TenantTag
        # Include organization so GraphQL queries can inspect which org a tag belongs to
        fields = ("id", "name", "slug", "organization")

    def resolve_usage_count(self, info):
        user = info.context.user
        if user.is_anonymous:
            return 0
        # Count usage on graphs and legacy playbooks within the user's org
        from tags.models import TaggedGraph, TaggedPlaybook
        graphs = TaggedGraph.objects.filter(tag=self, content_object__organization=user.organization).count()
        plays = TaggedPlaybook.objects.filter(tag=self, content_object__organization=user.organization).count()
        return graphs + plays

class Query(graphene.ObjectType):
    all_tags = graphene.List(TagType, description="Retrieves all tags belonging to the user's organization.")

    def resolve_all_tags(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")
        
        # CRITICAL: Only return tags belonging to the user's organization
        return TenantTag.objects.filter(organization=user.organization)

class CreateTag(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)

    tag = graphene.Field(TagType)

    class Meta:
        description = "Creates a new tag for the user's organization. If a tag with the same name already exists, it will be returned instead."

    @staticmethod
    def mutate(root, info, name):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        tag, created = TenantTag.objects.get_or_create(
            name=name,
            organization=user.organization
        )
        return CreateTag(tag=tag)

# This is the missing part that fixes the error
class Mutation(graphene.ObjectType):
    create_tag = CreateTag.Field()
