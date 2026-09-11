from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0013_platformcredential_test_fields'),
        ('playbooks', '0037_add_threat_surface'),
        ('rules', '0016_detectionrule_format_add_opentide'),
        ('identity', '0008_password_reset_token'),
    ]

    operations = [
        migrations.CreateModel(
            name='OpenTidePublishProfile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('branch', models.CharField(default='main', max_length=255)),
                ('target_folder', models.CharField(blank=True, default='', max_length=255)),
                ('enabled_platforms', models.JSONField(blank=True, default=list, help_text='Default deployment platforms for HEF publish jobs.')),
                ('use_graph_configured_platforms', models.BooleanField(default=True, help_text='Use workbench configured_platforms when no explicit platforms are set on the profile.')),
                ('enabled', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_opentide_publish_profiles', to='identity.customuser')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='opentide_publish_profiles', to='organizations.organization')),
                ('repository', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='opentide_publish_profiles', to='rules.rulerepository')),
            ],
            options={
                'verbose_name': 'OpenTIDE HEF Publish Profile',
                'verbose_name_plural': 'OpenTIDE HEF Publish Profiles',
                'ordering': ['name'],
                'unique_together': {('organization', 'name')},
            },
        ),
        migrations.CreateModel(
            name='OpenTideHefPublishJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('QUEUED', 'Queued'), ('PROCESSING', 'Processing'), ('COMPLETED', 'Completed'), ('FAILED', 'Failed')], default='QUEUED', max_length=20)),
                ('progress', models.TextField(blank=True, default='')),
                ('commit_message', models.TextField(blank=True, default='')),
                ('branch', models.CharField(default='main', max_length=255)),
                ('target_folder', models.CharField(blank=True, default='', max_length=255)),
                ('requested_platforms', models.JSONField(blank=True, default=list)),
                ('deployed_platforms', models.JSONField(blank=True, default=list)),
                ('deployment_results', models.JSONField(blank=True, default=list)),
                ('commit_sha', models.CharField(blank=True, default='', max_length=40)),
                ('github_url', models.CharField(blank=True, default='', max_length=1024)),
                ('file_paths', models.JSONField(blank=True, default=list)),
                ('error_message', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hef_publish_jobs', to='organizations.organization')),
                ('playbook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hef_publish_jobs', to='playbooks.playbookgraph')),
                ('profile', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='publish_jobs', to='organizations.opentidepublishprofile')),
                ('repository', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='hef_publish_jobs', to='rules.rulerepository')),
                ('rule', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='hef_publish_jobs', to='rules.detectionrule')),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='opentide_hef_publish_jobs', to='identity.customuser')),
            ],
            options={
                'verbose_name': 'OpenTIDE HEF Publish Job',
                'verbose_name_plural': 'OpenTIDE HEF Publish Jobs',
                'ordering': ['-created_at'],
            },
        ),
    ]