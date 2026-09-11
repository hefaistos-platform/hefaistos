"""
Migration 0010 – ATT&CK v19 readiness

Changes:
  * MitreAttackTechnique: add ``tactic``, ``revoked``, ``deprecated`` fields
  * New model: PlatformDataVersion (tracks loaded framework version per domain)
"""
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('platform_data', '0009_sharetideindexentry'),
    ]

    operations = [
        # --- 1. New fields on MitreAttackTechnique ---
        migrations.AddField(
            model_name='mitreattacktechnique',
            name='tactic',
            field=models.CharField(
                blank=True,
                max_length=255,
                help_text='ATT&CK tactic(s) for this technique (comma-separated if multiple)',
            ),
        ),
        migrations.AddField(
            model_name='mitreattacktechnique',
            name='revoked',
            field=models.BooleanField(
                default=False,
                help_text='Technique has been revoked by MITRE (superseded or removed)',
            ),
        ),
        migrations.AddField(
            model_name='mitreattacktechnique',
            name='deprecated',
            field=models.BooleanField(
                default=False,
                help_text='Technique has been deprecated by MITRE',
            ),
        ),

        # --- 2. PlatformDataVersion model ---
        migrations.CreateModel(
            name='PlatformDataVersion',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('framework', models.CharField(
                    choices=[
                        ('enterprise-attack', 'MITRE ATT&CK Enterprise'),
                        ('ics-attack', 'MITRE ATT&CK ICS'),
                        ('mobile-attack', 'MITRE ATT&CK Mobile'),
                        ('d3fend', 'MITRE D3FEND'),
                    ],
                    help_text="Framework identifier (e.g. 'enterprise-attack')",
                    max_length=50,
                    unique=True,
                )),
                ('version', models.CharField(
                    help_text="Loaded version string (e.g. '19.0')",
                    max_length=20,
                )),
                ('imported_at', models.DateTimeField(
                    auto_now=True,
                    help_text='Timestamp of the last successful import for this framework',
                )),
            ],
            options={
                'verbose_name': 'Platform Data Version',
                'verbose_name_plural': 'Platform Data Versions',
            },
        ),
    ]
