import uuid

from django.conf import settings
from django.db import models


class AIPrompt(models.Model):
    CATEGORY_CHOICES = [
        ('ANALYTICS', 'Analytics & Insights'),
        ('THREAT_HUNTING', 'Threat Hunting'),
        ('COMPLIANCE', 'Compliance & Reporting'),
        ('OPERATIONS', 'Operational Efficiency'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, help_text='Short descriptive title')
    description = models.TextField(help_text='What this prompt does')
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='ANALYTICS')
    prompt_template = models.TextField(
        help_text='Jinja2 template for the AI prompt. Use {{variables}} for dynamic context.'
    )
    is_system = models.BooleanField(
        default=True,
        help_text='System prompts are pre-loaded and cannot be deleted by users',
    )
    is_active = models.BooleanField(default=True, help_text='Inactive prompts are hidden from UI')
    required_role = models.CharField(
        max_length=10,
        choices=[('ADMIN', 'Admin Only'), ('REVIEWER', 'Reviewer and Above')],
        default='REVIEWER',
        help_text='Minimum role required to execute this prompt',
    )
    order = models.IntegerField(default=0, help_text='Display order within category')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_prompts',
    )

    class Meta:
        ordering = ['category', 'order', 'title']
        verbose_name = 'AI Prompt'
        verbose_name_plural = 'AI Prompts'

    def __str__(self):
        return f'[{self.category}] {self.title}'


class MonthlyReportSnapshot(models.Model):
    """Stores a monthly snapshot of MGMT Cave statistics for trend analysis."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='monthly_snapshots',
    )
    year = models.IntegerField()
    month = models.IntegerField()
    stats_json = models.JSONField(help_text='Full statistics payload for this month')
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'year', 'month')
        ordering = ['year', 'month']
        verbose_name = 'Monthly Report Snapshot'
        verbose_name_plural = 'Monthly Report Snapshots'

    def __str__(self):
        return f'{self.organization} {self.year}-{self.month:02d}'


class ReportMailingList(models.Model):
    """Tracks which users receive monthly scheduled report emails."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='report_mailing_entry',
    )
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='mailing_list_members',
    )
    is_subscribed = models.BooleanField(
        default=True,
        help_text='Whether the user is currently on the mailing list',
    )
    subscribed_at = models.DateTimeField(auto_now_add=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='removed_mailing_entries',
    )

    class Meta:
        ordering = ['user__username']
        verbose_name = 'Report Mailing List Entry'
        verbose_name_plural = 'Report Mailing List'

    def __str__(self):
        status = 'subscribed' if self.is_subscribed else 'unsubscribed'
        return f'{self.user.username} ({status})'
