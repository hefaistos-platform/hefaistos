"""GraphQL for Maieutic 3.0 sessions. Visibility and locking live in maieutic_lifecycle."""

import graphene
from graphene.types.generic import GenericScalar
from graphql import GraphQLError

from identity.decorators import Roles, role_required

from . import maieutic_lifecycle as lifecycle
from .maieutic_lifecycle import MaieuticError
from .maieutic_models import MaieuticDraft


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except MaieuticError as exc:
        raise GraphQLError(str(exc))


def _user(info):
    user = info.context.user
    if user.is_anonymous:
        raise GraphQLError('Authentication required')
    return user


class MaieuticDraftType(graphene.ObjectType):
    """Author view. Includes the spec. Never returned to anyone but the author."""
    id = graphene.UUID()
    name = graphene.String()
    status = graphene.String()
    current_stage = graphene.Int()
    spec = GenericScalar()
    outcome = graphene.String()
    created_workbench_id = graphene.UUID()
    finished_at = graphene.DateTime()
    allow_remote_pull = graphene.Boolean()
    tlp_classification = graphene.String()
    imported_from = graphene.String()
    is_locked = graphene.Boolean()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()

    def resolve_created_workbench_id(self, info):
        return self.created_workbench_id

    def resolve_is_locked(self, info):
        return self.status == MaieuticDraft.Status.FINISHED


class MaieuticAdminRowType(graphene.ObjectType):
    """Metadata only (spec 9b). Deliberately has no spec, answers or transcript field."""
    id = graphene.UUID()
    name = graphene.String()
    author_username = graphene.String()
    organization_name = graphene.String()
    status = graphene.String()
    outcome = graphene.String()
    current_stage = graphene.Int()
    tlp_classification = graphene.String()
    allow_remote_pull = graphene.Boolean()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()
    finished_at = graphene.DateTime()

    def resolve_author_username(self, info):
        return self.author.username if self.author else None

    def resolve_organization_name(self, info):
        return self.organization.name


class Query(graphene.ObjectType):
    maieutic_drafts = graphene.List(MaieuticDraftType, status=graphene.String())
    maieutic_draft = graphene.Field(MaieuticDraftType, id=graphene.UUID(required=True))
    maieutic_admin_index = graphene.List(MaieuticAdminRowType)

    @role_required([Roles.ADMIN, Roles.ANALYST])
    def resolve_maieutic_drafts(self, info, status=None):
        qs = lifecycle.list_visible_drafts(_user(info))
        if status:
            qs = qs.filter(status=status)
        return qs

    @role_required([Roles.ADMIN, Roles.ANALYST])
    def resolve_maieutic_draft(self, info, id):
        return lifecycle.get_visible_draft(_user(info), id)

    @role_required([Roles.ADMIN])
    def resolve_maieutic_admin_index(self, info):
        return _guard(lifecycle.admin_index, _user(info))


class CreateMaieuticDraft(graphene.Mutation):
    class Arguments:
        name = graphene.String()
        tlp_classification = graphene.String()

    draft = graphene.Field(MaieuticDraftType)

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, name=None, tlp_classification=None):
        return CreateMaieuticDraft(draft=lifecycle.create_draft(
            _user(info), name=name, tlp=tlp_classification))


class UpdateMaieuticDraft(graphene.Mutation):
    class Arguments:
        draft_id = graphene.UUID(required=True)
        name = graphene.String()
        current_stage = graphene.Int()
        spec_patch = GenericScalar()
        tlp_classification = graphene.String()

    draft = graphene.Field(MaieuticDraftType)

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, draft_id, name=None, current_stage=None, spec_patch=None, tlp_classification=None):
        return UpdateMaieuticDraft(draft=_guard(
            lifecycle.update_draft, draft_id, _user(info), name=name, current_stage=current_stage,
            spec_patch=spec_patch, tlp=tlp_classification))


class SetMaieuticDraftSharing(graphene.Mutation):
    class Arguments:
        draft_id = graphene.UUID(required=True)
        allow_remote_pull = graphene.Boolean(required=True)

    draft = graphene.Field(MaieuticDraftType)

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, draft_id, allow_remote_pull):
        return SetMaieuticDraftSharing(draft=_guard(
            lifecycle.set_sharing, draft_id, _user(info), allow=allow_remote_pull))


class DeleteMaieuticDraft(graphene.Mutation):
    class Arguments:
        draft_id = graphene.UUID(required=True)

    ok = graphene.Boolean()

    @staticmethod
    @role_required([Roles.ADMIN, Roles.ANALYST])
    def mutate(root, info, draft_id):
        _guard(lifecycle.delete_draft, draft_id, _user(info))
        return DeleteMaieuticDraft(ok=True)


class Mutation(graphene.ObjectType):
    create_maieutic_draft = CreateMaieuticDraft.Field()
    update_maieutic_draft = UpdateMaieuticDraft.Field()
    set_maieutic_draft_sharing = SetMaieuticDraftSharing.Field()
    delete_maieutic_draft = DeleteMaieuticDraft.Field()
