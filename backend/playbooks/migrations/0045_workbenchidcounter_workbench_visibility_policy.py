from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0044_mve_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='workbenchidcounter',
            name='workbench_visibility_policy',
            field=models.JSONField(blank=True, default=dict, help_text='System-level workbench visibility policy overrides.'),
        ),
    ]
