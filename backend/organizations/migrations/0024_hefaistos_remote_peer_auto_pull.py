from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0023_hefaistos_instance_sharing'),
    ]

    operations = [
        migrations.AddField(
            model_name='hefaistosremotepeer',
            name='auto_pull_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Enable scheduled automatic PULL from this remote peer.',
            ),
        ),
        migrations.AddField(
            model_name='hefaistosremotepeer',
            name='auto_pull_schedule',
            field=models.CharField(
                choices=[('DAILY', 'Daily'), ('WEEKLY', 'Weekly')],
                default='DAILY',
                help_text='Automatic PULL frequency when auto_pull_enabled is on.',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='hefaistosremotepeer',
            name='next_auto_pull_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Next scheduled automatic PULL time.',
                null=True,
            ),
        ),
    ]
