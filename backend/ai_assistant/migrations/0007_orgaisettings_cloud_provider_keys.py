from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0006_add_org_ai_settings_and_use_org_ai'),
    ]

    operations = [
        migrations.AddField(
            model_name='orgaisettings',
            name='openai_api_key',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='orgaisettings',
            name='gemini_api_key',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='orgaisettings',
            name='claude_api_key',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='orgaisettings',
            name='org_preferred_model',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Default model for org-wide AI usage, e.g. GPT-5, GEMINI-3-FLASH-PREVIEW, CLAUDE-SONNET-4.5, OLLAMA',
                max_length=50,
            ),
        ),
    ]
