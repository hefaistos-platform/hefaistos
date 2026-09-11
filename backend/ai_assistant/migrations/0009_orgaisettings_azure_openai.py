from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0008_add_opentide_ai_enrichment_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='orgaisettings',
            name='azure_openai_endpoint',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Azure OpenAI endpoint URL, e.g. https://YOUR_RESOURCE.openai.azure.com',
                max_length=512,
            ),
        ),
        migrations.AddField(
            model_name='orgaisettings',
            name='azure_openai_api_key',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='orgaisettings',
            name='azure_openai_deployment',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Azure OpenAI deployment name',
                max_length=100,
            ),
        ),
    ]
