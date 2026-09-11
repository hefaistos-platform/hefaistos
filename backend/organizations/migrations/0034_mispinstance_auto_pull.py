from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0033_billing_profile_and_manager_access'),
    ]

    operations = [
        migrations.AddField(
            model_name='mispinstance',
            name='auto_pull_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Enable scheduled automatic Waiting Room import from this MISP instance.',
            ),
        ),
        migrations.AddField(
            model_name='mispinstance',
            name='auto_pull_schedule',
            field=models.CharField(
                choices=[('HOURLY', 'Hourly'), ('DAILY', 'Daily'), ('WEEKLY', 'Weekly')],
                default='DAILY',
                help_text='Automatic import frequency when auto_pull_enabled is on.',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='mispinstance',
            name='auto_pull_tag',
            field=models.CharField(
                blank=True,
                default='HEFAISTOS',
                help_text='Only import events carrying this tag during scheduled auto-pull. Empty means import all events.',
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name='mispinstance',
            name='next_auto_pull_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Next scheduled automatic import time.',
                null=True,
            ),
        ),
    ]
