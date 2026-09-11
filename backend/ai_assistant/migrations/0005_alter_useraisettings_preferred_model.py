from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0004_merge_20251222_0000'),
    ]

    operations = [
        migrations.AlterField(
            model_name='useraisettings',
            name='preferred_model',
            field=models.CharField(
                choices=[
                    ('GPT-5.2', 'GPT-5.2'),
                    ('GPT-5.1', 'GPT-5.1'),
                    ('GPT-5', 'GPT-5'),
                    ('GPT-4', 'GPT-4'),
                    ('GPT-3.5', 'GPT-3.5'),
                    ('GEMINI-3.1-PRO-PREVIEW', 'Gemini 3.1 Pro Preview'),
                    ('GEMINI-3-PRO-PREVIEW', 'Gemini 3 Pro Preview'),
                    ('GEMINI-3-FLASH-PREVIEW', 'Gemini 3 Flash Preview'),
                    ('GEMINI-3.0-PRO', 'Gemini 3.0 Pro'),
                    ('GEMINI-2.5-FLASH', 'Gemini 2.5 Flash'),
                    ('GEMINI-PRO', 'Gemini (Legacy)'),
                    ('GEMINI-2.5-FLASH-LITE', 'Gemini 2.5 Flash Lite'),
                    ('CLAUDE-OPUS-4.5', 'Claude Opus 4.5'),
                    ('CLAUDE-SONNET-4.5', 'Claude Sonnet 4.5'),
                    ('CLAUDE-HAIKU-4.5', 'Claude Haiku 4.5'),
                    ('CLAUDE-3', 'Claude 3'),
                ],
                default='GEMINI-3-FLASH-PREVIEW',
                max_length=50,
            ),
        ),
    ]
