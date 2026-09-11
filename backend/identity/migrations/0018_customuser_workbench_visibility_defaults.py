from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0017_customuser_session_timeout_hours'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='workbench_visibility_defaults',
            field=models.JSONField(blank=True, default=dict, help_text='Per-user workbench section visibility defaults.'),
        ),
    ]
