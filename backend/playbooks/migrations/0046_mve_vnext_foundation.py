from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("playbooks", "0045_workbenchidcounter_workbench_visibility_policy"),
    ]

    operations = [
        migrations.AddField(
            model_name="mvedraft",
            name="analytic_family",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="mvedraft",
            name="primary_methodology",
            field=models.CharField(default="volumetric_de", max_length=64),
        ),
        migrations.AddField(
            model_name="mvedraft",
            name="behavior_object",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="mvedraft",
            name="dimensions",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="mvedraft",
            name="measurement_model",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="mvedraft",
            name="time_window_logic",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="mvedraft",
            name="baseline_strategy",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="mvedraft",
            name="context_risk",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="mvedraft",
            name="generation_profile",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="mvedraft",
            name="downstream_handoff",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="mvenode",
            name="node_config",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="mvenode",
            name="node_type",
            field=models.CharField(
                choices=[
                    ("EVENT", "Event"),
                    ("RULE", "Rule"),
                    ("FEATURE", "Feature"),
                    ("BASELINE", "Baseline"),
                    ("CONTEXT", "Context"),
                    ("DECEPTION", "Deception"),
                    ("DECISION", "Decision"),
                ],
                max_length=10,
            ),
        ),
    ]
