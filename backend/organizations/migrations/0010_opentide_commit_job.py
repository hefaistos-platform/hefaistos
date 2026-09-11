import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0009_playbookcommithistory_timeout_status'),
        ('playbooks', '0033_playbookgraph_opentide_ai_enrichment'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OpenTideCommitJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(
                    choices=[
                        ('QUEUED', 'Queued'),
                        ('PROCESSING', 'Processing'),
                        ('COMPLETED', 'Completed'),
                        ('FAILED', 'Failed'),
                    ],
                    default='QUEUED',
                    max_length=20,
                )),
                ('progress', models.TextField(blank=True, default='')),
                ('commit_message', models.TextField(blank=True, default='')),
                ('use_ai_enrichment', models.BooleanField(default=True)),
                ('force_bdr_generation', models.BooleanField(default=False)),
                ('field_overrides', models.JSONField(blank=True, default=list)),
                ('commit_sha', models.CharField(blank=True, default='', max_length=40)),
                ('file_paths', models.JSONField(blank=True, default=list)),
                ('error_message', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='commit_jobs',
                    to='organizations.organization',
                )),
                ('playbook', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='commit_jobs',
                    to='playbooks.playbookgraph',
                )),
                ('user', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='opentide_commit_jobs',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'OpenTide Commit Job',
                'verbose_name_plural': 'OpenTide Commit Jobs',
                'ordering': ['-created_at'],
            },
        ),
    ]
