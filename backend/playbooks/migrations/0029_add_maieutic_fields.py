# Generated manually for Maieutic Engine enhancements

from django.db import migrations, models
from django.db.models import JSONField


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0028_playbooknode_mitre_attack_mappings_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='playbookgraph',
            name='data_source_maturity',
            field=models.CharField(
                max_length=20,
                null=True,
                blank=True,
                choices=[
                    ('APPLICATION', 'Application'),
                    ('USER_MODE', 'User-Mode'),
                    ('KERNEL_MODE', 'Kernel-Mode'),
                ],
                help_text='Data source maturity level from Maieutic Engine'
            ),
        ),
        migrations.AddField(
            model_name='playbookgraph',
            name='conversation_history',
            field=JSONField(
                default=list,
                blank=True,
                help_text='Maieutic Engine conversation log for audit trail'
            ),
        ),
    ]
