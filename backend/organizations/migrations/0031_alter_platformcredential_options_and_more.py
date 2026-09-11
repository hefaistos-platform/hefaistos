from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0030_opentidehefpublishjob_failure_summary"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="platformcredential",
            options={
                "ordering": ["platform", "profile_name"],
                "verbose_name": "Platform Credential",
                "verbose_name_plural": "Platform Credentials",
            },
        ),
        migrations.AlterField(
            model_name="hefaistosinboundsharekey",
            name="allowed_scopes",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Allowed pull scopes for this key: WORKBENCH, RULES, ACH, ADVOPS, ALL.",
            ),
        ),
    ]
