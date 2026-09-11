from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0019_rulerepository_provider_and_api_base_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='rulerepository',
            name='verify_ssl',
            field=models.BooleanField(
                default=True,
                help_text='Verify TLS certificates for repository API calls. Disable only for trusted self-signed endpoints.',
            ),
        ),
    ]
