"""Capture evidence automatically; classify errors only after explicit user submission."""
import copy
import difflib
import re

from django.db import transaction
from django.utils import timezone
from graphql import GraphQLError

from .models import (AIRuleGenerationArtifact, AIRuleRevision, AIRuleLineage,
                     AIRuleFeedback, AIFeedbackAuditEvent)
from .prompt_registry import digest, require_prompt_admin

ISSUE_CATEGORIES = ('incorrect_table', 'incorrect_field', 'incorrect_logic', 'syntax',
                    'missing_context', 'false_positives', 'output_structure', 'formatting',
                    'changed_requirements', 'other')
VERIFICATIONS = ('NOT_TESTED', 'SYNTAX_CHECKED', 'SAMPLE_DATA_TESTED', 'REVIEWER_APPROVED')
ROOT_CAUSES = ('UNKNOWN', 'PROMPT', 'CONTEXT', 'RETRIEVAL', 'SCHEMA_MAPPING',
               'APPLICATION', 'MODEL', 'USER_PREFERENCE')
SUPPORTED_FORMATS = ('KQL', 'EQL', 'SPL', 'WAZUH', 'AQL', 'OTHER')


def require_writer(user):
    if (not user or not user.is_authenticated or not user.is_active
            or user.role in {'BOT_AUDITOR_ORG', 'BOT_AUDITOR_GLOBAL'}
            or not (user.is_superuser or user.role in {'ADMIN', 'ANALYST'})):
        raise GraphQLError('Only analysts and administrators can submit rule corrections.')
    if user.organization_id is None:
        raise GraphQLError('Rule feedback requires an organization.')


def clean_generated_rule(content):
    """Match the rule editor's established cleanup without changing detection logic."""
    cleaned = content.strip()
    fence = re.search(r'```[a-zA-Z]*\s*\n([\s\S]*?)\n?```', cleaned)
    cleaned = fence.group(1).strip() if fence else re.sub(r'^```[a-zA-Z]*\s*$', '', cleaned, flags=re.M).strip()
    cleaned = cleaned.replace('\t', '  ')
    prose = re.compile(r'^(?:\*\*.*\*\*|\*.*\*|#{1,6}\s|>\s|\d+\.\s|\s*[-*+]\s+[A-Z]|[A-Za-z][A-Za-z\s,]+[.!?]$)')
    rule_line = re.compile(r'^(?://|#|title:|id:|status:|name:|description:|detection:|let\s|index=|\||<[a-zA-Z]|[A-Za-z_]+\s*[:=|])')
    lines = cleaned.split('\n')
    start = 0
    for index, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        if rule_line.search(line):
            start = index
            break
        if prose.search(line):
            start = index + 1
    return '\n'.join(lines[start:]).strip()


@transaction.atomic
def capture_generation(user, bundle, output_format, provenance, *, task=None,
                       workbench_id=None, context_kind='standalone', context_id=None):
    if not user.organization_id or output_format not in SUPPORTED_FORMATS:
        return {}
    artifacts = {}
    for variant, key in (('primary', 'primary_rule'), ('quick_win', 'quick_win_rule'), ('robust', 'robust_rule')):
        raw = bundle.get(key) or ''
        content = clean_generated_rule(raw)
        if not content or content.lower().startswith(('# error', 'error:')):
            continue
        values = dict(organization_id=user.organization_id, created_by=user,
                      author_username=user.username, output_format=output_format, variant=variant,
                      workbench_id=str(workbench_id or ''), context_kind=context_kind,
                      context_id=str(context_id or workbench_id or ''), raw_content=raw,
                      content=content, content_hash=digest(content), prompt_provenance=copy.deepcopy(provenance))
        if task:
            artifact, created = AIRuleGenerationArtifact.objects.get_or_create(task=task, variant=variant, defaults=values)
            if not created and (artifact.content != content or artifact.prompt_provenance != provenance):
                raise GraphQLError('This generation already has different captured evidence.')
        else:
            artifact = AIRuleGenerationArtifact.objects.create(**values)
        artifacts[variant] = artifact
    return artifacts


def _event(feedback, user, action, reason=''):
    AIFeedbackAuditEvent.objects.create(feedback=feedback, actor=user,
        actor_username=user.username, action=action, reason=reason)


def validate_attribution(user, rule, output_format, artifact_id=None, detach=False):
    require_writer(user)
    if rule.organization_id != user.organization_id:
        raise GraphQLError('Rule is outside your organization.')
    if artifact_id and detach:
        raise GraphQLError('Cannot attach and detach an AI generation at the same time.')
    if not artifact_id:
        return None
    artifact = AIRuleGenerationArtifact.objects.filter(pk=artifact_id, organization_id=user.organization_id,
                                                       output_format=output_format).first()
    if not artifact:
        raise GraphQLError('AI generation does not match this organization and rule format.')
    if artifact.workbench_id and artifact.workbench_id != str(rule.playbook_id or ''):
        raise GraphQLError('AI generation belongs to a different Workbench.')
    if not artifact.workbench_id and artifact.created_by_id != user.pk and not (user.is_superuser or user.role == 'ADMIN'):
        # Collaborators can continue already established lineage, but cannot claim
        # another user's unrelated standalone generation as a new source.
        if not AIRuleLineage.objects.filter(rule=rule, output_format=output_format, active_artifact=artifact).exists():
            raise GraphQLError('This standalone generation belongs to another user.')
    return artifact


@transaction.atomic
def record_rule_revision(user, rule, output_format, editor_content, *, artifact_id=None, detach=False):
    if output_format not in SUPPORTED_FORMATS:
        if artifact_id:
            raise GraphQLError('AI feedback is unsupported for this rule format.')
        return None
    artifact = validate_attribution(user, rule, output_format, artifact_id, detach)
    lineage, _ = AIRuleLineage.objects.get_or_create(rule=rule, output_format=output_format)
    lineage = AIRuleLineage.objects.select_for_update().select_related('latest_revision').get(pk=lineage.pk)
    artifact = artifact if artifact_id else (None if detach else lineage.active_artifact)
    content = editor_content.replace('\r\n', '\n').strip()
    content_hash = digest(content)
    previous = lineage.latest_revision
    if previous and previous.content_hash == content_hash and previous.generation_artifact_id == (artifact.id if artifact else None):
        return previous
    revision = AIRuleRevision.objects.create(organization_id=user.organization_id, rule=rule,
        rule_snapshot_id=str(rule.pk), rule_title=rule.title, workbench_id=str(rule.playbook_id or ''),
        output_format=output_format, number=(previous.number if previous else 0) + 1,
        created_by=user, author_username=user.username, generation_artifact=artifact,
        editor_content=content, saved_content=rule.raw_content, content_hash=content_hash)
    # Earlier unsubmitted diffs remain evidence but no longer represent the current save.
    pending = AIRuleFeedback.objects.filter(revision__rule=rule, revision__output_format=output_format,
                                            status=AIRuleFeedback.Status.CANDIDATE)
    for old in pending.select_for_update():
        old.status = AIRuleFeedback.Status.SUPERSEDED
        old.save(update_fields=['status'])
        _event(old, user, 'SUPERSEDED', 'A newer saved revision replaced this correction candidate.')
    lineage.latest_revision = revision
    lineage.active_artifact = artifact
    lineage.save(update_fields=['latest_revision', 'active_artifact'])
    if artifact and content != artifact.content.replace('\r\n', '\n').strip():
        feedback = AIRuleFeedback.objects.create(organization_id=user.organization_id, revision=revision)
        _event(feedback, user, 'CANDIDATE_CREATED')
    return revision


def _owned_feedback(user, feedback_id):
    require_writer(user)
    feedback = AIRuleFeedback.objects.select_related('revision__generation_artifact').filter(
        pk=feedback_id, organization_id=user.organization_id).first()
    if not feedback or (feedback.revision.created_by_id != user.pk and not (user.is_superuser or user.role == 'ADMIN')):
        raise GraphQLError('Correction feedback not found or not owned by you.')
    return feedback


def record_document_revisions(user, rule, document, attributions=None):
    fields = {'KQL': ('kql', 'query'), 'EQL': ('elastic', 'query'), 'SPL': ('spl', 'query'),
              'WAZUH': ('wazuh', 'rule'), 'AQL': ('qradar', 'query')}
    sources = {}
    for entry in attributions or []:
        entry = dict(entry)
        fmt = entry.get('output_format')
        if fmt not in fields or fmt in sources:
            raise GraphQLError('AI attributions must specify each supported format at most once.')
        sources[fmt] = entry
    existing = set(AIRuleLineage.objects.filter(rule=rule).values_list('output_format', flat=True))
    platforms = document.get('platforms', {})
    for fmt, (platform, key) in fields.items():
        if platform in platforms or fmt in existing or fmt in sources:
            source = sources.get(fmt, {})
            record_rule_revision(user, rule, fmt, (platforms.get(platform) or {}).get(key, ''),
                artifact_id=source.get('generation_artifact_id'), detach=source.get('detach', False))


def _text(value, label, *, required=True, maximum=4000):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()) or '\x00' in value:
        raise GraphQLError(f'{label} must be text of {"1" if required else "0"}–{maximum} characters.')
    return value.strip()


@transaction.atomic
def submit_feedback(user, feedback_id, issues, verification, verification_evidence=''):
    feedback = _owned_feedback(user, feedback_id)
    feedback = AIRuleFeedback.objects.select_for_update().get(pk=feedback.pk)
    if feedback.status != AIRuleFeedback.Status.CANDIDATE:
        raise GraphQLError('Only current correction candidates can be submitted.')
    if not isinstance(issues, list) or not 1 <= len(issues) <= 10:
        raise GraphQLError('Provide between one and ten correction issues.')
    validated = []
    for issue in issues:
        if not isinstance(issue, dict) or set(issue) - {'category', 'explanation', 'resolution', 'before', 'after'}:
            raise GraphQLError('Invalid correction issue fields.')
        if issue.get('category') not in ISSUE_CATEGORIES:
            raise GraphQLError('Unknown correction category.')
        item = {'category': issue['category'],
                'explanation': _text(issue.get('explanation'), 'What was wrong'),
                'resolution': _text(issue.get('resolution'), 'How it was resolved')}
        for key in ('before', 'after'):
            if key in issue:
                item[key] = _text(issue[key], key, required=False)
        validated.append(item)
    if verification not in VERIFICATIONS:
        raise GraphQLError('Unknown verification level.')
    evidence = _text(verification_evidence, 'Verification evidence', required=verification != 'NOT_TESTED')
    feedback.issues = validated
    feedback.verification = verification
    feedback.verification_evidence = evidence
    feedback.status = AIRuleFeedback.Status.SUBMITTED
    feedback.submitted_by = user
    feedback.submitted_username = user.username
    feedback.submitted_at = timezone.now()
    feedback.save(update_fields=['issues', 'verification', 'verification_evidence', 'status',
                                 'submitted_by', 'submitted_username', 'submitted_at'])
    _event(feedback, user, 'SUBMITTED')
    return feedback


@transaction.atomic
def dismiss_feedback(user, feedback_id, reason):
    feedback = _owned_feedback(user, feedback_id)
    feedback = AIRuleFeedback.objects.select_for_update().get(pk=feedback.pk)
    if feedback.status != AIRuleFeedback.Status.CANDIDATE:
        raise GraphQLError('Only correction candidates can be dismissed.')
    feedback.status = AIRuleFeedback.Status.DISMISSED
    feedback.save(update_fields=['status'])
    _event(feedback, user, 'DISMISSED', _text(reason, 'Dismissal reason'))
    return feedback


@transaction.atomic
def review_feedback(user, feedback_id, accept, root_cause, note):
    feedback = AIRuleFeedback.objects.select_related('revision__generation_artifact').filter(pk=feedback_id).first()
    if not feedback:
        raise GraphQLError('Feedback not found.')
    require_prompt_admin(user, feedback.organization_id)
    feedback = AIRuleFeedback.objects.select_for_update().get(pk=feedback.pk)
    if feedback.status != AIRuleFeedback.Status.SUBMITTED:
        raise GraphQLError('Only submitted feedback can be reviewed.')
    if root_cause not in ROOT_CAUSES:
        raise GraphQLError('Unknown root cause.')
    feedback.status = AIRuleFeedback.Status.ACCEPTED if accept else AIRuleFeedback.Status.REJECTED
    feedback.reviewed_by = user
    feedback.reviewed_username = user.username
    feedback.reviewed_at = timezone.now()
    feedback.review_note = _text(note, 'Review reason')
    feedback.root_cause = root_cause
    feedback.save(update_fields=['status', 'reviewed_by', 'reviewed_username', 'reviewed_at', 'review_note', 'root_cause'])
    _event(feedback, user, feedback.status, feedback.review_note)
    return feedback


def feedback_payload(feedback):
    revision = feedback.revision
    artifact = revision.generation_artifact
    diff = ''.join(difflib.unified_diff([line + '\n' for line in artifact.content.splitlines()],
                                      [line + '\n' for line in revision.editor_content.splitlines()],
                                      fromfile='AI generated rule', tofile=f'saved revision {revision.number}'))
    return {'schema_version': 1, 'component': artifact.component, 'operation': artifact.operation,
            'feedback_id': str(feedback.id), 'status': feedback.status,
            'scope': {'organization_id': str(feedback.organization_id), 'workbench_id': revision.workbench_id or None,
                      'output_format': revision.output_format},
            'generation': {'artifact_id': str(artifact.id), 'task_id': str(artifact.task_id) if artifact.task_id else None,
                           'context_kind': artifact.context_kind, 'context_id': artifact.context_id or None,
                           'raw_output': artifact.raw_content,
                           'variant': artifact.variant, 'author': artifact.author_username,
                           'content_hash': artifact.content_hash, 'prompt_provenance': artifact.prompt_provenance},
            'correction': {'rule_id': revision.rule_snapshot_id, 'revision_id': str(revision.id), 'number': revision.number,
                           'author': revision.author_username, 'content_hash': revision.content_hash,
                           'before': artifact.content, 'after': revision.editor_content, 'diff': diff},
            'issues': feedback.issues, 'verification': {'level': feedback.verification,
                'evidence': feedback.verification_evidence, 'source': 'user_reported'},
            'submission': {'user': feedback.submitted_username, 'at': feedback.submitted_at.isoformat() if feedback.submitted_at else None},
            'review': {'user': feedback.reviewed_username, 'at': feedback.reviewed_at.isoformat() if feedback.reviewed_at else None,
                       'root_cause': feedback.root_cause, 'note': feedback.review_note}}
