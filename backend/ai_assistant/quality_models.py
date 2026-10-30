"""Deployment-local prompt versions. These records are never repository assets."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class AIPromptLock(models.Model):
    """Serialize changes across scopes, including changes to inherited prompts."""
    prompt_key = models.CharField(max_length=100, primary_key=True)


class AIPromptConfiguration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prompt_key = models.CharField(max_length=100)
    # NULL denotes installation scope; organization overrides are isolated.
    organization = models.ForeignKey('organizations.Organization', null=True, blank=True,
                                     on_delete=models.CASCADE)
    language = models.CharField(max_length=12, default='*')
    active_version = models.ForeignKey('AIPromptVersion', null=True, blank=True,
                                       on_delete=models.RESTRICT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['prompt_key', 'language', 'organization'],
                                    condition=models.Q(organization__isnull=False),
                                    name='ai_prompt_org_scope_unique'),
            models.UniqueConstraint(fields=['prompt_key', 'language'],
                                    condition=models.Q(organization__isnull=True),
                                    name='ai_prompt_install_scope_unique'),
        ]


class AIPromptVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(AIPromptConfiguration, on_delete=models.CASCADE,
                                      related_name='versions')
    number = models.PositiveIntegerField()
    instructions = models.TextField()
    content_hash = models.CharField(max_length=64)
    # Optimistic check against the effective prompt shown to the draft author.
    base_fingerprint = models.CharField(max_length=64)
    base_instructions = models.TextField()
    change_reason = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                   on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name='+')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ['-number']
        constraints = [models.UniqueConstraint(fields=['configuration', 'number'],
                                               name='ai_prompt_version_number_unique')]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = type(self).objects.get(pk=self.pk)
            immutable = ('configuration_id', 'number', 'instructions', 'content_hash',
                         'base_fingerprint', 'base_instructions', 'change_reason', 'created_by_id')
            if any(getattr(original, field) != getattr(self, field) for field in immutable):
                raise ValidationError('Prompt versions are immutable. Create a new draft.')
        return super().save(*args, **kwargs)


class AIPromptAuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(AIPromptConfiguration, on_delete=models.CASCADE,
                                      related_name='events')
    version = models.ForeignKey(AIPromptVersion, null=True, blank=True,
                                on_delete=models.RESTRICT, related_name='+')
    previous_version = models.ForeignKey(AIPromptVersion, null=True, blank=True,
                                         on_delete=models.RESTRICT, related_name='+')
    action = models.CharField(max_length=24)
    reason = models.TextField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                              on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
