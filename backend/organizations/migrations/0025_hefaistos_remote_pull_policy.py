from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0024_hefaistos_remote_peer_auto_pull'),
    ]

    operations = [
        migrations.AddField(
            model_name='hefaistosinboundsharekey',
            name='enforce_tag_filter',
            field=models.BooleanField(
                default=False,
                help_text='When enabled, remote pulls are restricted to items matching required_tags.',
            ),
        ),
        migrations.AddField(
            model_name='hefaistosinboundsharekey',
            name='required_tags',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Required tags for export eligibility when enforce_tag_filter is enabled (e.g. ["PULL"]).',
            ),
        ),
        migrations.AlterField(
            model_name='hefaistospulljob',
            name='requested_scope',
            field=models.CharField(
                choices=[
                    ('WORKBENCH', 'Workbench'),
                    ('RULES', 'Rules'),
                    ('ACH', 'ACH'),
                    ('ADVOPS', 'ADVOPS'),
                    ('ALL', 'All'),
                ],
                default='ALL',
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name='hefaistosremotepeer',
            name='default_scope',
            field=models.CharField(
                choices=[
                    ('WORKBENCH', 'Workbench'),
                    ('RULES', 'Rules'),
                    ('ACH', 'ACH'),
                    ('ADVOPS', 'ADVOPS'),
                    ('ALL', 'All'),
                ],
                default='ALL',
                help_text='Default content range to pull from the remote instance.',
                max_length=16,
            ),
        ),
    ]
