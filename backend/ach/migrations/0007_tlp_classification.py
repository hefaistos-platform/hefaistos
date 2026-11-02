from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ach', '0006_achanalysis_allow_remote_pull')]

    operations = [
        migrations.AddField(
            model_name='achanalysis',
            name='tlp_classification',
            field=models.CharField(choices=[('CLEAR', 'TLP:CLEAR - Public disclosure'), ('GREEN', 'TLP:GREEN - Community sharing'), ('AMBER', 'TLP:AMBER - Limited disclosure'), ('AMBER+STRICT', 'TLP:AMBER+STRICT - Organization only'), ('RED', 'TLP:RED - Personal for named recipients'), ('UNCLEAR', 'TLP:UNCLEAR - Source or sharing model unknown, unclear, or not used (tlp-unclear.org)')], default='UNCLEAR', max_length=20),
        ),
        migrations.AddField(
            model_name='achtemplate',
            name='tlp_classification',
            field=models.CharField(choices=[('CLEAR', 'TLP:CLEAR - Public disclosure'), ('GREEN', 'TLP:GREEN - Community sharing'), ('AMBER', 'TLP:AMBER - Limited disclosure'), ('AMBER+STRICT', 'TLP:AMBER+STRICT - Organization only'), ('RED', 'TLP:RED - Personal for named recipients'), ('UNCLEAR', 'TLP:UNCLEAR - Source or sharing model unknown, unclear, or not used (tlp-unclear.org)')], default='UNCLEAR', max_length=20),
        ),
    ]
