from django.db import migrations, models


SCOPES = [
    ('WORKBENCH', 'Workbench'),
    ('RULES', 'Rules'),
    ('ACH', 'ACH'),
    ('ADVOPS', 'ADVOPS'),
    ('CAPABILITY', 'Capability Abstraction Library'),
    ('ALL', 'All'),
]


class Migration(migrations.Migration):
    dependencies = [
        ('organizations', '0034_mispinstance_auto_pull'),
    ]

    operations = [
        migrations.AlterField(
            model_name='hefaistosremotepeer',
            name='default_scope',
            field=models.CharField(
                max_length=16, choices=SCOPES, default='ALL',
                help_text='Default content range to pull from the remote instance.',
            ),
        ),
        migrations.AlterField(
            model_name='hefaistospulljob',
            name='requested_scope',
            field=models.CharField(max_length=16, choices=SCOPES, default='ALL'),
        ),
        migrations.AlterField(
            model_name='hefaistosinboundsharekey',
            name='allowed_scopes',
            field=models.JSONField(
                blank=True, default=list,
                help_text='Allowed pull scopes for this key: WORKBENCH, RULES, ACH, ADVOPS, CAPABILITY, ALL.',
            ),
        ),
    ]
