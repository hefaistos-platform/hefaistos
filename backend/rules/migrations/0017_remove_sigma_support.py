"""
Migration: Remove SIGMA support from HEFAISTOS platform.

Data changes:
- Remap all DetectionRule records with format='SIGMA' to format='OTHER'
- Remove SigmaKeyword table
- Update FORMAT_CHOICES to remove SIGMA option
"""

from django.db import migrations, models


def remap_sigma_rules(apps, schema_editor):
    """Remap existing SIGMA rules to OTHER format."""
    DetectionRule = apps.get_model('rules', 'DetectionRule')
    updated = DetectionRule.objects.filter(format='SIGMA').update(format='OTHER')
    if updated:
        print(f"  Remapped {updated} SIGMA rule(s) to OTHER format.")


def remap_sigma_rules_reverse(apps, schema_editor):
    """No-op reverse: cannot recover original SIGMA content."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0016_detectionrule_format_add_opentide'),
    ]

    operations = [
        # 1) Data migration: remap SIGMA → OTHER
        migrations.RunPython(remap_sigma_rules, remap_sigma_rules_reverse),

        # 2) Remove SIGMA from FORMAT_CHOICES on the model field
        migrations.AlterField(
            model_name='detectionrule',
            name='format',
            field=models.CharField(
                choices=[
                    ('KQL', 'Kusto Query Language'),
                    ('WAZUH', 'Wazuh XML'),
                    ('SPL', 'Splunk SPL'),
                    ('OPENTIDE', 'OpenTide Multi-Platform'),
                    ('OTHER', 'Other'),
                ],
                default='KQL',
                max_length=10,
            ),
        ),

        # 3) Drop SigmaKeyword table
        migrations.DeleteModel(
            name='SigmaKeyword',
        ),
    ]
