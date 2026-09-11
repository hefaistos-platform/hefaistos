import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0018_dacdeploymentconfig_and_hef_job_source'),
        ('identity', '0008_password_reset_token'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OpenTideHefImportJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('repo_owner', models.CharField(blank=True, default='', max_length=255)),
                ('repo_name', models.CharField(blank=True, default='', max_length=255)),
                ('branch', models.CharField(default='main', max_length=255)),
                ('target_folder', models.CharField(blank=True, default='', max_length=255)),
                ('source_commit_sha', models.CharField(blank=True, default='', max_length=40)),
                ('selected_bundles', models.JSONField(blank=True, default=list, help_text='List of bundle paths selected for import')),
                ('conflict_mode', models.CharField(choices=[('NEW_COPY', 'Create new copy'), ('OVERWRITE', 'Overwrite existing by MDR UUID'), ('SKIP', 'Skip if UUID already exists')], default='NEW_COPY', max_length=20)),
                ('import_platform_rules', models.BooleanField(default=True)),
                ('dry_run', models.BooleanField(default=False)),
                ('status', models.CharField(choices=[('QUEUED', 'Queued'), ('PROCESSING', 'Processing'), ('COMPLETED', 'Completed'), ('FAILED', 'Failed')], default='QUEUED', max_length=20)),
                ('progress', models.TextField(blank=True, default='')),
                ('results', models.JSONField(blank=True, default=list, help_text='Per-bundle import results [{bundle_path, workbench_id, status, errors}]')),
                ('error_message', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hef_import_jobs', to='organizations.organization')),
                ('profile', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='import_jobs', to='organizations.opentidepublishprofile')),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='opentide_hef_import_jobs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'OpenTIDE HEF Import Job',
                'verbose_name_plural': 'OpenTIDE HEF Import Jobs',
                'ordering': ['-created_at'],
            },
        ),
    ]
