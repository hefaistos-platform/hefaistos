import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0011_opentidecommitjob_raw_yaml_overrides'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlatformCredential',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('platform', models.CharField(
                    choices=[
                        ('defender', 'Microsoft Defender'),
                        ('sentinel', 'Azure Sentinel'),
                        ('splunk', 'Splunk'),
                        ('qradar', 'IBM QRadar'),
                        ('wazuh', 'Wazuh'),
                    ],
                    max_length=50,
                )),
                ('credentials_json', models.TextField(
                    db_column='credentials_json',
                    help_text='Encrypted JSON blob of platform credentials (do not access directly)',
                )),
                ('enabled', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='platform_credentials',
                    to='organizations.organization',
                )),
            ],
            options={
                'verbose_name': 'Platform Credential',
                'verbose_name_plural': 'Platform Credentials',
                'ordering': ['platform'],
                'unique_together': {('organization', 'platform')},
            },
        ),
    ]
