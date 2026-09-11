from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0031_alter_platformcredential_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='workbench_visibility_policy',
            field=models.JSONField(blank=True, default=dict, help_text='Organization-level workbench visibility policy overrides.'),
        ),
    ]
