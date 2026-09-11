import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0005_alter_useraisettings_preferred_model'),
        ('organizations', '0004_mispinstance'),
    ]

    operations = [
        migrations.AddField(
            model_name='useraisettings',
            name='use_org_ai',
            field=models.BooleanField(
                default=False,
                help_text='When True, use the organization-wide AI model instead of personal API keys.',
            ),
        ),
        migrations.CreateModel(
            name='OrgAISettings',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ollama_base_url', models.CharField(
                    blank=True,
                    default='',
                    help_text='Ollama server base URL, e.g. http://ollama:11434',
                    max_length=512,
                )),
                ('ollama_model', models.CharField(
                    blank=True,
                    default='',
                    help_text='Ollama model name, e.g. llama3, mistral, codellama',
                    max_length=100,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='ai_settings',
                    to='organizations.organization',
                )),
            ],
            options={
                'verbose_name': 'Organization AI Settings',
                'verbose_name_plural': 'Organization AI Settings',
            },
        ),
    ]
