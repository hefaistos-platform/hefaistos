import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0034_add_testing_tuning_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OpentidePreviewTask',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pending'),
                        ('RUNNING', 'Running'),
                        ('COMPLETED', 'Completed'),
                        ('FAILED', 'Failed'),
                    ],
                    default='PENDING',
                    max_length=20,
                )),
                ('use_ai_enrichment', models.BooleanField(default=True)),
                ('force_bdr_generation', models.BooleanField(default=False)),
                ('result_data', models.JSONField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('playbook', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='opentide_preview_tasks',
                    to='playbooks.playbookgraph',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='opentide_preview_tasks',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
