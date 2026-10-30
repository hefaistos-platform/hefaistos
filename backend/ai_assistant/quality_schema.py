"""AI Quality APIs use explicit approval authorization, not general configuration access."""

from difflib import unified_diff

import graphene
from graphene_django import DjangoObjectType
from graphql import GraphQLError

from .models import AIPromptConfiguration, AIPromptVersion, AIPromptAuditEvent
from .prompt_defaults import PROMPT_DEFAULTS
from .prompt_registry import (create_draft, require_prompt_admin, resolve_prompt,
                              restore_version, review_version, validate_key_language)


def _scope(user, organization_id=None, installation=False):
    if installation:
        if organization_id is not None:
            raise GraphQLError('Installation scope cannot specify an organization.')
        scope = None
    else:
        scope = organization_id or getattr(user, 'organization_id', None)
        if scope is None:
            raise GraphQLError('Select an organization or installation scope.')
    require_prompt_admin(user, scope)
    return scope


class PromptVersionType(DjangoObjectType):
    improvement_proposal_id = graphene.UUID()
    created_by_username = graphene.String()
    reviewed_by_username = graphene.String()
    diff = graphene.String()

    class Meta:
        model = AIPromptVersion
        fields = ('id', 'number', 'instructions', 'base_instructions', 'content_hash',
                  'base_fingerprint', 'change_reason', 'status', 'created_at',
                  'reviewed_at', 'review_note')
        convert_choices_to_enum = False

    def resolve_created_by_username(self, info):
        return self.created_by.username if self.created_by else None

    def resolve_reviewed_by_username(self, info):
        return self.reviewed_by.username if self.reviewed_by else None

    def resolve_diff(self, info):
        return ''.join(unified_diff(self.base_instructions.splitlines(keepends=True),
                                    self.instructions.splitlines(keepends=True),
                                    fromfile='previous instructions', tofile='proposed instructions'))

    def resolve_improvement_proposal_id(self, info):
        return self.improvement_proposal.id if hasattr(self, 'improvement_proposal') else None


class PromptAuditType(DjangoObjectType):
    actor_username = graphene.String()
    version_number = graphene.Int()
    previous_version_number = graphene.Int()

    class Meta:
        model = AIPromptAuditEvent
        fields = ('id', 'action', 'reason', 'created_at')

    def resolve_actor_username(self, info):
        return self.actor.username if self.actor else None

    def resolve_version_number(self, info):
        return self.version.number if self.version else None

    def resolve_previous_version_number(self, info):
        return self.previous_version.number if self.previous_version else None


class QualityPromptType(graphene.ObjectType):
    prompt_key = graphene.String(required=True)
    title = graphene.String(required=True)
    component = graphene.String(required=True)
    language = graphene.String(required=True)
    configuration_id = graphene.UUID()
    active_version_id = graphene.UUID()
    default_version = graphene.String(required=True)
    default_instructions = graphene.String(required=True)
    effective_instructions = graphene.String(required=True)
    effective_source = graphene.String(required=True)
    effective_version = graphene.String(required=True)
    effective_fingerprint = graphene.String(required=True)
    inherited_instructions = graphene.String(required=True)
    inherited_source = graphene.String(required=True)
    inherited_fingerprint = graphene.String(required=True)
    versions = graphene.List(PromptVersionType, required=True)
    events = graphene.List(PromptAuditType, required=True)


class Query(graphene.ObjectType):
    ai_quality_prompts = graphene.List(QualityPromptType, organization_id=graphene.UUID(),
                                       installation=graphene.Boolean(default_value=False),
                                       language=graphene.String(default_value='*'))

    def resolve_ai_quality_prompts(self, info, organization_id=None, installation=False, language='*'):
        scope = _scope(info.context.user, organization_id, installation)
        results = []
        for key, default in PROMPT_DEFAULTS.items():
            validate_key_language(key, language)
            effective = resolve_prompt(key, organization_id=scope, language=language)
            config = AIPromptConfiguration.objects.filter(
                prompt_key=key, organization_id=scope, language=language,
            ).first()
            inherited = resolve_prompt(key, organization_id=scope, language=language,
                                       skip_configuration_id=config.id if config else None)
            results.append(QualityPromptType(
                prompt_key=key, title=default['title'], component=default['component'],
                language=language, configuration_id=config.id if config else None,
                active_version_id=config.active_version_id if config else None,
                default_version=default['version'], default_instructions=default['instructions'],
                effective_instructions=effective.instructions, effective_source=effective.source,
                effective_version=effective.version, effective_fingerprint=effective.fingerprint,
                inherited_instructions=inherited.instructions, inherited_source=inherited.source,
                inherited_fingerprint=inherited.fingerprint,
                versions=list(config.versions.select_related('created_by', 'reviewed_by')[:50]) if config else [],
                events=list(config.events.select_related('actor', 'version', 'previous_version')[:100]) if config else [],
            ))
        return results


class CreateQualityPromptDraft(graphene.Mutation):
    class Arguments:
        prompt_key = graphene.String(required=True)
        organization_id = graphene.UUID()
        installation = graphene.Boolean(default_value=False)
        language = graphene.String(default_value='*')
        instructions = graphene.String(required=True)
        change_reason = graphene.String(required=True)
        base_fingerprint = graphene.String(required=True)

    version = graphene.Field(PromptVersionType)

    @staticmethod
    def mutate(root, info, prompt_key, instructions, change_reason, base_fingerprint,
               organization_id=None, installation=False, language='*'):
        scope = _scope(info.context.user, organization_id, installation)
        version = create_draft(info.context.user, prompt_key=prompt_key, organization_id=scope,
                               language=language, instructions=instructions,
                               change_reason=change_reason, base_fingerprint=base_fingerprint)
        return CreateQualityPromptDraft(version=version)


class ReviewQualityPromptVersion(graphene.Mutation):
    class Arguments:
        version_id = graphene.UUID(required=True)
        approve = graphene.Boolean(required=True)
        review_note = graphene.String(required=True)

    version = graphene.Field(PromptVersionType)

    @staticmethod
    def mutate(root, info, version_id, approve, review_note):
        version = review_version(info.context.user, version_id=version_id, approve=approve,
                                 review_note=review_note)
        return ReviewQualityPromptVersion(version=version)


class RestoreQualityPromptVersion(graphene.Mutation):
    class Arguments:
        configuration_id = graphene.UUID(required=True)
        version_id = graphene.UUID()
        reason = graphene.String(required=True)
        expected_fingerprint = graphene.String(required=True)
        inherited_fingerprint = graphene.String()

    configuration_id = graphene.UUID()

    @staticmethod
    def mutate(root, info, configuration_id, reason, expected_fingerprint,
               version_id=None, inherited_fingerprint=None):
        config = restore_version(info.context.user, configuration_id=configuration_id,
                                 version_id=version_id, reason=reason,
                                 expected_fingerprint=expected_fingerprint,
                                 inherited_fingerprint=inherited_fingerprint)
        return RestoreQualityPromptVersion(configuration_id=config.id)


class Mutation(graphene.ObjectType):
    create_quality_prompt_draft = CreateQualityPromptDraft.Field()
    review_quality_prompt_version = ReviewQualityPromptVersion.Field()
    restore_quality_prompt_version = RestoreQualityPromptVersion.Field()
