"""Resolve approved prompts and manage their explicit review lifecycle."""

import hashlib
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from graphql import GraphQLError

from .models import AIPromptAuditEvent, AIPromptConfiguration, AIPromptVersion, AIPromptLock
from .prompt_defaults import PROMPT_DEFAULTS, PROMPT_LANGUAGES


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def require_prompt_admin(user, organization_id):
    # Deliberately no is_staff or username-based service-account bypass.
    if not user or not user.is_authenticated:
        raise GraphQLError('Authentication required.')
    if not user.is_active or user.role in {'BOT_AUDITOR_ORG', 'BOT_AUDITOR_GLOBAL'}:
        raise GraphQLError('This account cannot manage AI prompts.')
    if user.is_superuser:
        return
    if (user.role != 'ADMIN' or organization_id is None
            or str(user.organization_id) != str(organization_id)):
        raise GraphQLError('Only an organization admin or platform superuser can manage these prompts.')


def validate_key_language(prompt_key, language):
    if prompt_key not in PROMPT_DEFAULTS:
        raise GraphQLError('Unknown AI prompt.')
    if language not in PROMPT_LANGUAGES:
        raise GraphQLError('Unsupported prompt language.')


@dataclass(frozen=True)
class ResolvedPrompt:
    instructions: str
    source: str
    version: str
    content_hash: str
    fingerprint: str

    def provenance(self):
        return {'source': self.source, 'version': self.version,
                'content_hash': self.content_hash, 'fingerprint': self.fingerprint}


def resolve_prompt(prompt_key, *, organization_id=None, language='*', skip_configuration_id=None):
    validate_key_language(prompt_key, language)
    scopes = [organization_id, None] if organization_id is not None else [None]
    languages = [language, '*'] if language != '*' else ['*']
    # Organization-specific instructions take precedence over installation ones.
    for scope in scopes:
        for candidate_language in languages:
            config = AIPromptConfiguration.objects.select_related('active_version').filter(
                prompt_key=prompt_key, organization_id=scope, language=candidate_language,
            ).first()
            if config and config.id == skip_configuration_id:
                continue
            version = config.active_version if config else None
            if version and version.status == AIPromptVersion.Status.APPROVED:
                source = 'ORGANIZATION' if scope is not None else 'INSTALLATION'
                return ResolvedPrompt(version.instructions, source, str(version.id),
                                      version.content_hash, digest(f'{version.id}:{version.content_hash}'))
    default = PROMPT_DEFAULTS[prompt_key]
    content_hash = digest(default['instructions'])
    return ResolvedPrompt(default['instructions'], 'DEFAULT', default['version'], content_hash,
                          digest(f"{prompt_key}:{default['version']}:{content_hash}"))


def _reason(value):
    if not value or not value.strip() or len(value) > 4000:
        raise GraphQLError('Provide a reason between 1 and 4,000 characters.')
    return value.strip()


def _event(config, actor, action, reason, version=None, previous=None):
    AIPromptAuditEvent.objects.create(configuration=config, actor=actor, action=action,
                                     reason=reason, version=version, previous_version=previous)


def _lock(prompt_key):
    # Must be called inside a transaction before reading the effective baseline.
    AIPromptLock.objects.get_or_create(prompt_key=prompt_key)
    AIPromptLock.objects.select_for_update().get(pk=prompt_key)


@transaction.atomic
def create_draft(user, *, prompt_key, organization_id, language, instructions,
                 change_reason, base_fingerprint):
    require_prompt_admin(user, organization_id)
    validate_key_language(prompt_key, language)
    reason = _reason(change_reason)
    if not instructions or not instructions.strip() or len(instructions) > 20000:
        raise GraphQLError('Instructions must contain between 1 and 20,000 characters.')
    _lock(prompt_key)
    effective = resolve_prompt(prompt_key, organization_id=organization_id, language=language)
    if base_fingerprint != effective.fingerprint:
        raise GraphQLError('The effective prompt changed. Refresh and review it before creating a draft.')
    config, _ = AIPromptConfiguration.objects.get_or_create(
        prompt_key=prompt_key, organization_id=organization_id, language=language,
    )
    config = AIPromptConfiguration.objects.select_for_update().get(pk=config.pk)
    number = (config.versions.aggregate(maximum=Max('number'))['maximum'] or 0) + 1
    instructions = instructions.strip()
    version = AIPromptVersion.objects.create(
        configuration=config, number=number, instructions=instructions,
        content_hash=digest(instructions), base_fingerprint=base_fingerprint,
        base_instructions=effective.instructions,
        change_reason=reason, created_by=user,
    )
    _event(config, user, 'DRAFT_CREATED', reason, version)
    return version


@transaction.atomic
def review_version(user, *, version_id, approve, review_note):
    reason = _reason(review_note)
    try:
        version = AIPromptVersion.objects.select_related('configuration').get(pk=version_id)
    except AIPromptVersion.DoesNotExist:
        raise GraphQLError('Prompt version not found.')
    require_prompt_admin(user, version.configuration.organization_id)
    _lock(version.configuration.prompt_key)
    config = AIPromptConfiguration.objects.select_for_update().get(pk=version.configuration_id)
    version = AIPromptVersion.objects.select_for_update().get(pk=version_id)
    if version.status != AIPromptVersion.Status.DRAFT:
        raise GraphQLError('Only draft versions can be reviewed.')
    if approve:
        current = resolve_prompt(config.prompt_key, organization_id=config.organization_id,
                                 language=config.language)
        if current.fingerprint != version.base_fingerprint:
            raise GraphQLError('The effective prompt changed since this draft was created. Create a new draft.')
    version.status = AIPromptVersion.Status.APPROVED if approve else AIPromptVersion.Status.REJECTED
    version.reviewed_by = user
    version.reviewed_at = timezone.now()
    version.review_note = reason
    version.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_note'])
    previous = config.active_version
    if approve:
        config.active_version = version
        config.save(update_fields=['active_version'])
    _event(config, user, 'APPROVED_ACTIVATED' if approve else 'REJECTED', reason, version, previous)
    return version


@transaction.atomic
def restore_version(user, *, configuration_id, version_id, reason,
                    expected_fingerprint, inherited_fingerprint=None):
    reason = _reason(reason)
    try:
        config = AIPromptConfiguration.objects.get(pk=configuration_id)
    except AIPromptConfiguration.DoesNotExist:
        raise GraphQLError('Prompt configuration not found.')
    require_prompt_admin(user, config.organization_id)
    _lock(config.prompt_key)
    config = AIPromptConfiguration.objects.select_for_update().get(pk=configuration_id)
    current = resolve_prompt(config.prompt_key, organization_id=config.organization_id, language=config.language)
    if current.fingerprint != expected_fingerprint:
        raise GraphQLError('The effective prompt changed. Refresh before restoring a version.')
    version = None
    if version_id is not None:
        version = config.versions.filter(pk=version_id, status=AIPromptVersion.Status.APPROVED).first()
        if not version:
            raise GraphQLError('Only approved versions of this configuration can be restored.')
    else:
        inherited = resolve_prompt(config.prompt_key, organization_id=config.organization_id,
                                   language=config.language, skip_configuration_id=config.id)
        if inherited.fingerprint != inherited_fingerprint:
            raise GraphQLError('The inherited prompt changed. Refresh before resetting instructions.')
    previous = config.active_version
    config.active_version = version
    config.save(update_fields=['active_version'])
    _event(config, user, 'RESTORED' if version else 'RESET_TO_INHERITED', reason, version, previous)
    return config
