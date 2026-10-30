"""Frozen feedback proposals and evaluations remain deployment-local database evidence."""
import uuid

from django.conf import settings
from django.db import models

from .feedback_models import ImmutableEvidence


class AIImprovementProposal(ImmutableEvidence):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.OneToOneField('ai_assistant.AIPromptVersion', on_delete=models.CASCADE,
                                  related_name='improvement_proposal')
    evidence = models.JSONField(default=list)
    cases = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']


class AIImprovementEvaluation(ImmutableEvidence):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proposal = models.ForeignKey(AIImprovementProposal, on_delete=models.CASCADE, related_name='evaluations')
    task = models.OneToOneField('ai_assistant.AIGenerationTask', null=True, on_delete=models.SET_NULL)
    content_hash = models.CharField(max_length=64)
    base_fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']


class AIImprovementAssessment(ImmutableEvidence):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evaluation = models.OneToOneField(AIImprovementEvaluation, on_delete=models.CASCADE, related_name='assessment')
    cases = models.JSONField(default=list)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    reviewer_username = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)


class AIImprovementEvaluationResult(ImmutableEvidence):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evaluation = models.OneToOneField(AIImprovementEvaluation, on_delete=models.CASCADE, related_name='result')
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
