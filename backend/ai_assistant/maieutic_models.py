"""Maieutic Engine 3.0 session storage. See Docs/MAIEUTIC_3_SPEC.md sections 9 to 9c."""

import uuid

from django.conf import settings
from django.db import models

from playbooks.utils.tlp import TLP_CHOICES


class MaieuticDraft(models.Model):
    """One guided session. Author-only; locked permanently once FINISHED."""

    class Status(models.TextChoices):
        IN_PROGRESS = 'IN_PROGRESS', 'In progress'
        FINISHED = 'FINISHED', 'Finished'

    class Outcome(models.TextChoices):
        WORKBENCH_WITH_RULE = 'WORKBENCH_WITH_RULE', 'Workbench created, rule generation started'
        WORKBENCH_WITHOUT_RULE = 'WORKBENCH_WITHOUT_RULE', 'Workbench created without rule'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE, related_name='maieutic_drafts',
    )
    # SET_NULL so deleting a user does not destroy a finished design record.
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='maieutic_drafts',
    )
    name = models.CharField(max_length=255, default='New Maieutic session')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    current_stage = models.PositiveSmallIntegerField(default=1)
    spec = models.JSONField(default=dict, blank=True)
    ade_snapshot = models.ForeignKey(
        'platform_data.AdeSnapshot', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_workbench = models.ForeignKey(
        'playbooks.PlaybookGraph', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    outcome = models.CharField(max_length=30, choices=Outcome.choices, blank=True, default='')
    finished_at = models.DateTimeField(null=True, blank=True)
    allow_remote_pull = models.BooleanField(default=False)
    tlp_classification = models.CharField(max_length=20, choices=TLP_CHOICES, default='UNCLEAR')
    # Set when a session arrives through Instance Sharing; such sessions are born FINISHED.
    imported_from = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['organization', 'author', 'status']),
            models.Index(fields=['organization', 'updated_at']),
        ]

    def __str__(self):
        return f'{self.name} ({self.status})'
