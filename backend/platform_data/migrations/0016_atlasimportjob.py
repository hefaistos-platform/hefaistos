import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("platform_data", "0015_atlas_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="AtlasImportJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("source_repo", models.URLField(default="https://github.com/mitre-atlas/atlas-data", max_length=512)),
                ("source_ref", models.CharField(default="main", help_text="Git ref or commit SHA", max_length=100)),
                ("mode", models.CharField(choices=[("REMOTE", "Remote"), ("LOCAL", "Local")], default="REMOTE", max_length=10)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("RUNNING", "Running"), ("SUCCESS", "Success"), ("FAILED", "Failed")], default="PENDING", max_length=10)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("log", models.TextField(blank=True, default="")),
                ("error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("triggered_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="atlas_import_jobs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "ATLAS Import Job",
                "verbose_name_plural": "ATLAS Import Jobs",
                "ordering": ["-created_at"],
            },
        ),
    ]
