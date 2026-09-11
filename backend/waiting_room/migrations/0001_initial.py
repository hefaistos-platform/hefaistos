from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('organizations', '0031_alter_platformcredential_options_and_more'),
        ('playbooks', '0044_mve_models'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WaitingCase',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('source_type', models.CharField(choices=[('MANUAL', 'Manual'), ('MISP', 'MISP')], default='MANUAL', max_length=16)),
                ('misp_event_id', models.CharField(blank=True, default='', max_length=64)),
                ('title', models.CharField(max_length=255)),
                ('short_description', models.TextField(blank=True, default='')),
                ('detection_objective', models.TextField(blank=True, default='')),
                ('mapped_ttps', models.JSONField(blank=True, default=list)),
                ('estimated_detection_complexity', models.CharField(blank=True, default='', max_length=64)),
                ('raw_payload', models.JSONField(blank=True, default=dict)),
                ('status', models.CharField(choices=[('NEW', 'New'), ('ENRICHING', 'Enriching'), ('READY', 'Ready'), ('PROMOTED', 'Promoted'), ('FAILED', 'Failed')], default='NEW', max_length=20)),
                ('enrichment_error', models.TextField(blank=True, default='')),
                ('promoted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_waiting_cases', to=settings.AUTH_USER_MODEL)),
                ('misp_instance', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='waiting_cases', to='organizations.mispinstance')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='waiting_cases', to='organizations.organization')),
                ('promoted_graph', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='waiting_cases', to='playbooks.playbookgraph')),
            ],
            options={'ordering': ['-updated_at']},
        ),
        migrations.AddConstraint(
            model_name='waitingcase',
            constraint=models.UniqueConstraint(condition=models.Q(('misp_event_id__gt', '')), fields=('misp_instance', 'misp_event_id'), name='waiting_case_misp_instance_event_unique'),
        ),
        migrations.CreateModel(
            name='WaitingCaseEnrichmentTask',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('RUNNING', 'Running'), ('COMPLETED', 'Completed'), ('FAILED', 'Failed')], default='PENDING', max_length=20)),
                ('result_data', models.JSONField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('requested_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='waiting_case_enrichment_tasks', to=settings.AUTH_USER_MODEL)),
                ('waiting_case', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='enrichment_tasks', to='waiting_room.waitingcase')),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
