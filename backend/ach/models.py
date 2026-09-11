from django.db import models
from django.conf import settings
from data_catalog.models import DataSource
from platform_data.models import MitreAttackTechnique
from django.utils import timezone
import uuid

class ACHTemplate(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    hypotheses = models.JSONField(default=list, help_text="List of hypothesis strings")
    evidence = models.JSONField(default=list, help_text="List of evidence objects {'content': '...', 'credibility': '...'}")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class ACHAnalysis(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ach_analyses')
    STATUS_CHOICES = [
        ('RESEARCH', 'Research'),
        ('FINISHED', 'Finished'),
        ('APPROVED', 'Approved'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='RESEARCH')
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_ach_analyses'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    saved_as_template = models.BooleanField(default=False, help_text="Whether this analysis has been saved as a template")
    allow_remote_pull = models.BooleanField(
        default=False,
        help_text='If enabled, this ACH analysis can be exported to trusted remote HEFAISTOS peers.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name_plural = "ACH Analyses"

class Hypothesis(models.Model):
    analysis = models.ForeignKey(ACHAnalysis, on_delete=models.CASCADE, related_name='hypotheses')
    content = models.TextField()
    is_proven = models.BooleanField(default=False)
    sequence = models.IntegerField(default=0)
    mitre_technique = models.ForeignKey(MitreAttackTechnique, on_delete=models.SET_NULL, null=True, blank=True, related_name='ach_hypotheses')
    
    def __str__(self):
        return self.content[:50]
    
    class Meta:
        ordering = ['sequence']

class Evidence(models.Model):
    CREDIBILITY_CHOICES = [
        ('HIGH', 'High'),
        ('MEDIUM', 'Medium'),
        ('LOW', 'Low'),
    ]
    
    analysis = models.ForeignKey(ACHAnalysis, on_delete=models.CASCADE, related_name='evidence_items')
    content = models.TextField()
    credibility = models.CharField(max_length=10, choices=CREDIBILITY_CHOICES, default='MEDIUM')
    relevance = models.TextField(blank=True)
    sequence = models.IntegerField(default=0)
    
    # Linking fields
    data_source = models.ForeignKey(DataSource, on_delete=models.SET_NULL, null=True, blank=True, related_name='ach_evidence')
    log_reference = models.CharField(max_length=255, blank=True, help_text="Specific Log ID or Query")

    def __str__(self):
        return self.content[:50]

    class Meta:
        ordering = ['sequence']

class MatrixCell(models.Model):
    SCORE_CHOICES = [
        ('CC', 'Very Consistent'),
        ('C', 'Consistent'),
        ('N', 'Neutral'),
        ('I', 'Inconsistent'),
        ('II', 'Very Inconsistent'),
    ]
    
    hypothesis = models.ForeignKey(Hypothesis, on_delete=models.CASCADE, related_name='matrix_cells')
    evidence = models.ForeignKey(Evidence, on_delete=models.CASCADE, related_name='matrix_cells')
    score = models.CharField(max_length=2, choices=SCORE_CHOICES, default='N')
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('hypothesis', 'evidence')
