import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("data_catalog", "0001_initial"),
        ("rules", "0020_rulerepository_verify_ssl"),
        ("playbooks", "0043_playbookgraph_allow_remote_pull"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MveDraft",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(default="New Velocity Chain", max_length=255)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("VALIDATED", "Validated"), ("EXPORTED", "Exported")], default="DRAFT", max_length=20)),
                ("anchor_entity", models.CharField(default="host.hostname", max_length=255)),
                ("max_total_span_ms", models.PositiveIntegerField(default=800)),
                ("is_advops_validated", models.BooleanField(default=False)),
                ("validation_summary", models.JSONField(blank=True, default=dict)),
                ("last_validated_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("author", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="mve_drafts", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mve_drafts", to="organizations.organization")),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="MveValidationRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("RUNNING", "Running"), ("COMPLETED", "Completed"), ("FAILED", "Failed")], default="PENDING", max_length=20)),
                ("result_data", models.JSONField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("draft", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="validation_runs", to="playbooks.mvedraft")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="mve_validation_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="MveNode",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("step_order", models.PositiveIntegerField(default=1)),
                ("node_type", models.CharField(choices=[("EVENT", "Event"), ("RULE", "Rule")], max_length=10)),
                ("label", models.CharField(blank=True, default="", max_length=255)),
                ("tactic_ref", models.CharField(blank=True, default="", max_length=20)),
                ("technique_ref", models.CharField(blank=True, default="", max_length=20)),
                ("criteria", models.JSONField(blank=True, default=dict)),
                ("position_x", models.FloatField(default=120)),
                ("position_y", models.FloatField(default=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("capability_abstraction", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="mve_nodes", to="playbooks.capabilityabstraction")),
                ("data_source", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="mve_nodes", to="data_catalog.datasource")),
                ("detection_rule", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="mve_nodes", to="rules.detectionrule")),
                ("draft", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="nodes", to="playbooks.mvedraft")),
            ],
            options={
                "ordering": ["step_order", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="MveEdge",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("draft", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="edges", to="playbooks.mvedraft")),
                ("source_node", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="outgoing_edges", to="playbooks.mvenode")),
                ("target_node", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="incoming_edges", to="playbooks.mvenode")),
            ],
        ),
        migrations.AddIndex(
            model_name="mvedraft",
            index=models.Index(fields=["organization", "status"], name="playbooks_mv_organiz_0d6f4e_idx"),
        ),
        migrations.AddIndex(
            model_name="mvedraft",
            index=models.Index(fields=["organization", "updated_at"], name="playbooks_mv_organiz_58d7f7_idx"),
        ),
        migrations.AddIndex(
            model_name="mvenode",
            index=models.Index(fields=["draft", "step_order"], name="playbooks_mv_draft_i_2a6cb7_idx"),
        ),
        migrations.AddIndex(
            model_name="mvenode",
            index=models.Index(fields=["draft", "node_type"], name="playbooks_mv_draft_i_29f4d9_idx"),
        ),
        migrations.AddIndex(
            model_name="mveedge",
            index=models.Index(fields=["draft"], name="playbooks_mv_draft_i_2a8f8d_idx"),
        ),
        migrations.AddConstraint(
            model_name="mveedge",
            constraint=models.UniqueConstraint(fields=("draft", "source_node", "target_node"), name="uniq_mve_edge_per_draft"),
        ),
        migrations.AddIndex(
            model_name="mvevalidationrun",
            index=models.Index(fields=["draft", "created_at"], name="playbooks_mv_draft_i_e402e0_idx"),
        ),
        migrations.AddIndex(
            model_name="mvevalidationrun",
            index=models.Index(fields=["status"], name="playbooks_mv_status_a04b66_idx"),
        ),
    ]
