from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0032_playbookgraph_opentide'),
    ]

    operations = [
        migrations.AddField(
            model_name='playbookgraph',
            name='opentide_ai_enrichment',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text=(
                    'Cached AI-enriched threat fields for OpenTIDE export '
                    '(terrain, leverage, impact, viability, description).'
                ),
            ),
        ),
    ]
