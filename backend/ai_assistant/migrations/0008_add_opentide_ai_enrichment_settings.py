from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0007_orgaisettings_cloud_provider_keys'),
    ]

    operations = [
        migrations.AddField(
            model_name='useraisettings',
            name='enable_auto_enrichment',
            field=models.BooleanField(
                default=True,
                help_text='Automatically enrich OpenTIDE metadata using AI when information is missing',
            ),
        ),
        migrations.AddField(
            model_name='useraisettings',
            name='auto_generate_bdr',
            field=models.BooleanField(
                default=True,
                help_text='Automatically generate BDR schema for compliance-driven detections',
            ),
        ),
        migrations.AddField(
            model_name='useraisettings',
            name='auto_enrich_response',
            field=models.BooleanField(
                default=True,
                help_text='Automatically generate response procedures and supporting searches',
            ),
        ),
        migrations.AddField(
            model_name='useraisettings',
            name='auto_map_platforms',
            field=models.BooleanField(
                default=True,
                help_text='Automatically extract platforms and targets from technical context',
            ),
        ),
    ]
