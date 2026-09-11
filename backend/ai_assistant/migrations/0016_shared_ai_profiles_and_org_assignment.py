import uuid

import django.db.models.deletion
from django.db import migrations, models


def forward_seed_shared_ai(apps, schema_editor):
    OrgAISettings = apps.get_model('ai_assistant', 'OrgAISettings')
    SharedAIProfile = apps.get_model('ai_assistant', 'SharedAIProfile')

    source = (
        OrgAISettings.objects
        .filter(
            models.Q(ollama_base_url__gt='') |
            models.Q(openai_api_key__isnull=False) |
            models.Q(gemini_api_key__isnull=False) |
            models.Q(claude_api_key__isnull=False) |
            models.Q(azure_openai_endpoint__gt='') |
            models.Q(azure_openai_api_key__isnull=False)
        )
        .order_by('created_at', 'id')
        .first()
    )
    if source is None:
        return

    SharedAIProfile.objects.get_or_create(
        name='Default Shared AI',
        defaults={
            'ollama_base_url': source.ollama_base_url,
            'ollama_model': source.ollama_model,
            'openai_api_key': source.openai_api_key,
            'gemini_api_key': source.gemini_api_key,
            'claude_api_key': source.claude_api_key,
            'azure_openai_endpoint': source.azure_openai_endpoint,
            'azure_openai_api_key': source.azure_openai_api_key,
            'azure_openai_deployment': source.azure_openai_deployment,
            'org_preferred_model': source.org_preferred_model,
            'ollama_enabled': source.ollama_enabled,
            'openai_enabled': source.openai_enabled,
            'gemini_enabled': source.gemini_enabled,
            'claude_enabled': source.claude_enabled,
            'azure_openai_enabled': source.azure_openai_enabled,
            'is_active': True,
        },
    )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0015_alter_aigenerationtask_task_type_add_threat_report'),
    ]

    operations = [
        migrations.CreateModel(
            name='SharedAIProfile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120, unique=True)),
                ('ollama_base_url', models.CharField(blank=True, default='', max_length=512)),
                ('ollama_model', models.CharField(blank=True, default='', max_length=100)),
                ('openai_api_key', models.TextField(blank=True, null=True)),
                ('gemini_api_key', models.TextField(blank=True, null=True)),
                ('claude_api_key', models.TextField(blank=True, null=True)),
                ('azure_openai_endpoint', models.CharField(blank=True, default='', max_length=512)),
                ('azure_openai_api_key', models.TextField(blank=True, null=True)),
                ('azure_openai_deployment', models.CharField(blank=True, default='', max_length=100)),
                ('org_preferred_model', models.CharField(blank=True, default='', max_length=50)),
                ('ollama_enabled', models.BooleanField(default=True)),
                ('openai_enabled', models.BooleanField(default=True)),
                ('gemini_enabled', models.BooleanField(default=True)),
                ('claude_enabled', models.BooleanField(default=True)),
                ('azure_openai_enabled', models.BooleanField(default=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_shared_ai_profiles', to='identity.customuser')),
            ],
            options={
                'verbose_name': 'Shared AI Profile',
                'verbose_name_plural': 'Shared AI Profiles',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='orgaisettings',
            name='shared_profile',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_organizations', to='ai_assistant.sharedaiprofile'),
        ),
        migrations.AddField(
            model_name='orgaisettings',
            name='shared_profile_locked',
            field=models.BooleanField(default=False, help_text='When enabled, this organization must use the assigned shared AI profile.'),
        ),
        migrations.RunPython(forward_seed_shared_ai, noop_reverse),
    ]
