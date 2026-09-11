from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0010_opentide_commit_job'),
    ]

    operations = [
        migrations.AddField(
            model_name='opentidecommitjob',
            name='raw_yaml_overrides',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text=(
                    "Optional raw YAML strings edited by the user in the preview modal, "
                    "stored as {\"mdr\": \"...\", \"dom\": \"...\", \"bdr\": \"...\"}. "
                    "When present, the commit worker uses these strings instead of recompiling."
                ),
            ),
        ),
    ]
