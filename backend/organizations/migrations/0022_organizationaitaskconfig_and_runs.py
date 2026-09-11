import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0021_dac_mode_deploy_only'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OrganizationAITaskConfig',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('task_key', models.CharField(max_length=64)),
                ('enabled', models.BooleanField(default=False)),
                ('schedule', models.CharField(choices=[('DAILY', 'Daily'), ('WEEKLY', 'Weekly'), ('MONTHLY', 'Monthly')], default='WEEKLY', max_length=16)),
                ('day_of_week', models.PositiveSmallIntegerField(default=0, help_text='For WEEKLY schedules: 0=Monday ... 6=Sunday.', validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(6)])),
                ('day_of_month', models.PositiveSmallIntegerField(default=1, help_text='For MONTHLY schedules: day 1-28.', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(28)])),
                ('run_hour', models.PositiveSmallIntegerField(default=8, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(23)])),
                ('run_minute', models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(59)])),
                ('next_run_at', models.DateTimeField(blank=True, null=True)),
                ('last_run_at', models.DateTimeField(blank=True, null=True)),
                ('last_status', models.CharField(blank=True, choices=[('SUCCESS', 'Success'), ('FAILED', 'Failed'), ('SKIPPED', 'Skipped')], max_length=16, null=True)),
                ('last_message', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_task_configs', to='organizations.organization')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='updated_org_ai_task_configs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Organization AI Task Configuration',
                'verbose_name_plural': 'Organization AI Task Configurations',
                'ordering': ['task_key'],
                'unique_together': {('organization', 'task_key')},
            },
        ),
        migrations.CreateModel(
            name='OrganizationAITaskRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('task_key', models.CharField(max_length=64)),
                ('status', models.CharField(choices=[('SUCCESS', 'Success'), ('FAILED', 'Failed'), ('SKIPPED', 'Skipped')], max_length=16)),
                ('trigger', models.CharField(choices=[('SCHEDULED', 'Scheduled'), ('MANUAL', 'Manual')], default='SCHEDULED', max_length=16)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('duration_ms', models.PositiveIntegerField(blank=True, null=True)),
                ('output_summary', models.TextField(blank=True, default='')),
                ('error_message', models.TextField(blank=True, default='')),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_task_runs', to='organizations.organization')),
                ('run_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='org_ai_task_runs', to=settings.AUTH_USER_MODEL)),
                ('task_config', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='runs', to='organizations.organizationaitaskconfig')),
            ],
            options={
                'verbose_name': 'Organization AI Task Run',
                'verbose_name_plural': 'Organization AI Task Runs',
                'ordering': ['-started_at'],
                'indexes': [
                    models.Index(fields=['organization', 'task_key'], name='organization_ai_task_org_task_idx'),
                    models.Index(fields=['organization', 'started_at'], name='organization_ai_task_org_started_idx'),
                ],
            },
        ),
    ]

