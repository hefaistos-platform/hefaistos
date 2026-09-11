import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0003_organization_entity"),
    ]

    operations = [
        migrations.CreateModel(
            name="MISPInstance",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="misp_instances",
                        to="organizations.organization",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("url", models.CharField(max_length=512)),
                ("auth_key", models.TextField()),
                ("verify_ssl", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["created_at"],
                "unique_together": {("organization", "name")},
            },
        ),
    ]
