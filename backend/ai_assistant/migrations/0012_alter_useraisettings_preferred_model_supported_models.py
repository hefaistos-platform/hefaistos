from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0011_ai_generation_task'),
    ]

    operations = [
        migrations.AlterField(
            model_name='useraisettings',
            name='preferred_model',
            field=models.CharField(
                choices=[
                    ('GPT-5.5', 'GPT-5.5'),
                    ('GPT-5.4', 'GPT-5.4'),
                    ('GPT-5.4-MINI', 'GPT-5.4 Mini'),
                    ('GEMINI-3.1-PRO-PREVIEW', 'Gemini 3.1 Pro Preview'),
                    ('GEMINI-3.5-FLASH', 'Gemini 3.5 Flash'),
                    ('GEMINI-3-FLASH-PREVIEW', 'Gemini 3 Flash Preview'),
                    ('GEMINI-3.1-FLASH-LITE', 'Gemini 3.1 Flash Lite'),
                    ('GEMINI-3.1-FLASH-LITE-PREVIEW', 'Gemini 3.1 Flash Lite Preview'),
                    ('CLAUDE-OPUS-4.7', 'Claude Opus 4.7'),
                    ('CLAUDE-SONNET-4.6', 'Claude Sonnet 4.6'),
                    ('CLAUDE-HAIKU-4.5-20251001', 'Claude Haiku 4.5 (20251001)'),
                ],
                default='GEMINI-3.5-FLASH',
                max_length=50,
            ),
        ),
    ]
