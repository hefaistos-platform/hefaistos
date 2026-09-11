from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0015_alter_detectionrule_default_format_kql'),
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
                    ('OPENTIDE', 'OpenTide Multi-Platform'),
                    ('OTHER', 'Other'),
                ],
                default='KQL',
                max_length=10,
            ),
        ),
    ]
