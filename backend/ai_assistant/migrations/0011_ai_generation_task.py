import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0010_orgaisettings_provider_enabled_flags'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AIGenerationTask',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('task_type', models.CharField(
                    choices=[
                        ('GENERATE_SIGMA', 'Generate Rule'),
                        ('SUGGEST_IMPROVEMENTS', 'Suggest Improvements'),
                        ('GENERATE_SIMILAR', 'Generate Similar Rules'),
                    ],
                    max_length=30,
                )),
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
                ('input_data', models.JSONField()),
                ('result_data', models.JSONField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='ai_generation_tasks',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
