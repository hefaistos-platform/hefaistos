from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0014_detectionrule_format_add_spl'),
    ]

    operations = [
        migrations.AlterField(
            model_name='detectionrule',
            name='format',
            field=models.CharField(
                choices=[
                    ('SIGMA', 'Sigma YAML'),
                    ('KQL', 'Kusto Query Language'),
                    ('WAZUH', 'Wazuh XML'),
                    ('SPL', 'Splunk SPL'),
                    ('OTHER', 'Other'),
                ],
                default='KQL',
                max_length=10,
            ),
        ),
    ]
