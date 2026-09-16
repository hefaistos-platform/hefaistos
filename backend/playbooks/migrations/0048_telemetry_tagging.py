from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("playbooks", "0047_mve_statuses"),
    ]

    operations = [
        migrations.AddField(
            model_name="playbookgraph",
            name="telemetry_requirements",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "AI-derived/edited telemetry requirement tags for this Workbench "
                    "object. Always unverified reference-vocabulary hypotheses in this "
                    "milestone; see Docs/TELEMETRY_TAGGING.md."
                ),
            ),
        ),
        migrations.AddField(
            model_name="playbookgraph",
            name="telemetry_requirements_generated_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Timestamp of the last successful telemetry-tag derivation run.",
            ),
        ),
    ]
