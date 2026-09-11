from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0031_playbookgraph_minor_version'),
    ]

    operations = [
        migrations.AddField(
            model_name='playbookgraph',
            name='opentide_yaml',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text='OpenTide multi-platform YAML structure',
            ),
        ),
        migrations.AddField(
            model_name='playbookgraph',
            name='configured_platforms',
            field=models.JSONField(
                default=list,
                help_text="List of configured platforms: ['kql', 'spl', 'sigma', 'wazuh']",
            ),
        ),
    ]
