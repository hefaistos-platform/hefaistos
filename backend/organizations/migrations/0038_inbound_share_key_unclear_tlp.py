from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('organizations', '0037_inbound_share_key_tlp')]

    operations = [
        migrations.AlterField(
            model_name='hefaistosinboundsharekey',
            name='required_tlp_classification',
            field=models.CharField(
                max_length=20,
                default='RED',
                help_text='Maximum TLP includes lower levels and UNCLEAR; selecting UNCLEAR permits only UNCLEAR.',
                choices=[
                    ('CLEAR', 'TLP:CLEAR - Public disclosure'),
                    ('GREEN', 'TLP:GREEN - Community sharing'),
                    ('AMBER', 'TLP:AMBER - Limited disclosure'),
                    ('AMBER+STRICT', 'TLP:AMBER+STRICT - Organization only'),
                    ('RED', 'TLP:RED - Personal for named recipients'),
                    ('UNCLEAR', 'TLP:UNCLEAR - Source or sharing model unknown, unclear, or not used (tlp-unclear.org)'),
                ],
            ),
        ),
    ]
