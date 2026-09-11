import uuid
from django.db import models
from platform_data.models import MitreDataComponent

class LogSource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255) # e.g. "Sysmon Process Creation"
    
    # MITRE Mapping
    mitre_component = models.ForeignKey(MitreDataComponent, on_delete=models.SET_NULL, null=True, blank=True)
    mitre_log_provider = models.CharField(max_length=100, blank=True) # e.g. "WinEventLog:Sysmon"
    mitre_channel = models.CharField(max_length=100, blank=True) # e.g. "EventCode=1"
    
    # Internal SIEM Details
    siem_product = models.CharField(max_length=100, default='Elasticsearch')
    index_pattern = models.CharField(max_length=255, blank=True, help_text="e.g. winlogbeat-*")
    coverage_status = models.CharField(
        max_length=20, 
        choices=[('ACTIVE', 'Active'), ('PARTIAL', 'Partial'), ('MISSING', 'Missing')],
        default='ACTIVE'
    )

    def __str__(self):
        return f"{self.name} ({self.index_pattern})"

class LogField(models.Model):
    """
    The Schema: Maps standard names to actual SIEM fields.
    """
    log_source = models.ForeignKey(LogSource, related_name='fields', on_delete=models.CASCADE)
    standard_name = models.CharField(max_length=255) # e.g. "CommandLine"
    siem_field_name = models.CharField(max_length=255) # e.g. "winlog.event_data.CommandLine"
    field_type = models.CharField(max_length=50, default='keyword')
