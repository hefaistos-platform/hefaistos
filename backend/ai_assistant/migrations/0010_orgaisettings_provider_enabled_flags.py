from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0009_orgaisettings_azure_openai'),
    ]

    operations = [
        migrations.AddField(
            model_name='orgaisettings',
            name='ollama_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='orgaisettings',
            name='openai_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='orgaisettings',
            name='gemini_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='orgaisettings',
            name='claude_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='orgaisettings',
            name='azure_openai_enabled',
            field=models.BooleanField(default=True),
        ),
    ]
