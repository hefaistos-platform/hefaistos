from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0015_opentidepublishprofile_push_platform_rules'),
    ]

    operations = [
        migrations.AddField(
            model_name='opentidehefpublishjob',
            name='push_opentide_bundle',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='opentidehefpublishjob',
            name='push_platform_rules',
            field=models.BooleanField(default=False),
        ),
    ]
