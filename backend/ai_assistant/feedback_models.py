"""Immutable generation/correction evidence and explicitly reviewed feedback."""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ImmutableEvidence(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('AI quality evidence is immutable.')
        return super().save(*args, **kwargs)


class AIRuleGenerationArtifact(ImmutableEvidence):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE)
    task = models.ForeignKey('ai_assistant.AIGenerationTask', null=True, blank=True,
                             on_delete=models.SET_NULL, related_name='rule_artifacts')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    author_username = models.CharField(max_length=150)
    component = models.CharField(max_length=50, default='rule_generation')
    operation = models.CharField(max_length=50, default='generate')
    output_format = models.CharField(max_length=12)
    variant = models.CharField(max_length=20, default='primary')
    # Snapshot identifiers survive deletion of the originating context object.
    workbench_id = models.CharField(max_length=36, blank=True)
    context_kind = models.CharField(max_length=20, default='standalone')
    context_id = models.CharField(max_length=36, blank=True)
    raw_content = models.TextField()
    content = models.TextField()
    content_hash = models.CharField(max_length=64)
    prompt_provenance = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['task', 'variant'],
                         condition=models.Q(task__isnull=False), name='ai_rule_task_variant_unique')]


class AIRuleRevision(ImmutableEvidence):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE)
    rule = models.ForeignKey('rules.DetectionRule', null=True, on_delete=models.SET_NULL)
    rule_snapshot_id = models.CharField(max_length=40)
    rule_title = models.CharField(max_length=255)
    workbench_id = models.CharField(max_length=36, blank=True)
    output_format = models.CharField(max_length=12)
    number = models.PositiveIntegerField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    author_username = models.CharField(max_length=150)
    generation_artifact = models.ForeignKey(AIRuleGenerationArtifact, null=True, blank=True,
                                            on_delete=models.RESTRICT)
    editor_content = models.TextField()
    saved_content = models.TextField()
    content_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['rule', 'output_format', 'number'],
                                               name='ai_rule_revision_number_unique')]


class AIRuleLineage(models.Model):
    rule = models.ForeignKey('rules.DetectionRule', on_delete=models.CASCADE)
    output_format = models.CharField(max_length=12)
    active_artifact = models.ForeignKey(AIRuleGenerationArtifact, null=True, blank=True,
                                        on_delete=models.RESTRICT)
    latest_revision = models.ForeignKey(AIRuleRevision, null=True, blank=True,
                                        on_delete=models.RESTRICT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['rule', 'output_format'],
                                               name='ai_rule_lineage_format_unique')]


class AIRuleFeedback(models.Model):
    class Status(models.TextChoices):
        CANDIDATE = 'CANDIDATE', 'Awaiting user explanation'
        SUBMITTED = 'SUBMITTED', 'Awaiting admin review'
        ACCEPTED = 'ACCEPTED', 'Accepted for improvement analysis'
        REJECTED = 'REJECTED', 'Rejected'
        DISMISSED = 'DISMISSED', 'User dismissed'
        SUPERSEDED = 'SUPERSEDED', 'Replaced by a later correction'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE)
    revision = models.OneToOneField(AIRuleRevision, on_delete=models.CASCADE, related_name='feedback')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CANDIDATE)
    # User-provided classifications are stored separately from immutable evidence.
    issues = models.JSONField(default=list)
    verification = models.CharField(max_length=24, default='NOT_TESTED')
    verification_evidence = models.TextField(blank=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='+')
    submitted_username = models.CharField(max_length=150, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name='+')
    reviewed_username = models.CharField(max_length=150, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    root_cause = models.CharField(max_length=24, default='UNKNOWN')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']


class AIFeedbackAuditEvent(ImmutableEvidence):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feedback = models.ForeignKey(AIRuleFeedback, on_delete=models.CASCADE, related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_username = models.CharField(max_length=150)
    action = models.CharField(max_length=24)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
