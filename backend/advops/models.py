import uuid
from django.conf import settings
from django.db import models
from organizations.models import Organization


class ADVOPSReport(models.Model):
    class Status(models.TextChoices):
        IDEA = "IDEA", "Idea/Hypothesis"
        RESEARCH = "RESEARCH", "In Research"
        DEVELOPMENT = "DEVELOPMENT", "In Development"
        APPROVED = "APPROVED", "Approved"
        TESTING = "TESTING", "Testing"
        DEPLOYED = "DEPLOYED", "Deployed"
        TUNING = "TUNING", "Tuning/Maintenance"

    class Priority(models.TextChoices):
        CRITICAL = "CRITICAL", "Critical"
        HIGH = "HIGH", "High"
        MEDIUM = "MEDIUM", "Medium"
        LOW = "LOW", "Low"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hunt_id = models.CharField(max_length=64, unique=True)
    hypothesis = models.TextField(blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.IDEA)
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.MEDIUM)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="advops_reports")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="advops_reports")
    allow_remote_pull = models.BooleanField(
        default=False,
        help_text='If enabled, this ADVOPS hunt can be exported to trusted remote HEFAISTOS peers.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Optional phase summaries (keep lightweight)
    verification_summary = models.TextField(blank=True)
    infrastructure_summary = models.TextField(blank=True)
    pivot_summary = models.TextField(blank=True)
    false_positive_summary = models.TextField(blank=True)
    mitre_summary = models.TextField(blank=True)
    detection_logic_summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["status", "priority"])]

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return f"{self.hunt_id} ({self.status})"
