from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('advops', '0003_advopsreport_allow_remote_pull')]

    operations = [
        migrations.AddField(
            model_name='advopsreport',
            name='tlp_classification',
            field=models.CharField(choices=[('CLEAR', 'TLP:CLEAR - Public disclosure'), ('GREEN', 'TLP:GREEN - Community sharing'), ('AMBER', 'TLP:AMBER - Limited disclosure'), ('AMBER+STRICT', 'TLP:AMBER+STRICT - Organization only'), ('RED', 'TLP:RED - Personal for named recipients'), ('UNCLEAR', 'TLP:UNCLEAR - Source or sharing model unknown, unclear, or not used (tlp-unclear.org)')], default='UNCLEAR', max_length=20),
        ),
    ]
