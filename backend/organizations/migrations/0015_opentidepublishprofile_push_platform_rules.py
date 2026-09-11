from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0014_opentide_hef_publish'),
    ]

    operations = [
        migrations.AddField(
            model_name='opentidepublishprofile',
            name='push_platform_rules',
            field=models.BooleanField(
                default=False,
                help_text='When enabled, also push individual platform rule files (kql/, splunk/, sigma/, etc.) alongside the OpenTide bundle.',
            ),
        ),
    ]
