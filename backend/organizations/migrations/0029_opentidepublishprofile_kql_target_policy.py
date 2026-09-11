from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0028_platformcredential_profiles'),
    ]

    operations = [
        migrations.AddField(
            model_name='opentidepublishprofile',
            name='kql_target_policy',
            field=models.CharField(
                choices=[
                    ('defender', 'Defender'),
                    ('sentinel', 'Sentinel'),
                    ('both', 'Defender + Sentinel'),
                ],
                default='defender',
                help_text="Default target mapping for 'kql' platform values: defender, sentinel, or both.",
                max_length=16,
            ),
        ),
    ]
