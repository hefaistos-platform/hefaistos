from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0029_opentidepublishprofile_kql_target_policy'),
    ]

    operations = [
        migrations.AddField(
            model_name='opentidehefpublishjob',
            name='failure_summary',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
