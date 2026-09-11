from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ach', '0005_alter_achtemplate_id_alter_evidence_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='achanalysis',
            name='allow_remote_pull',
            field=models.BooleanField(
                default=False,
                help_text='If enabled, this ACH analysis can be exported to trusted remote HEFAISTOS peers.',
            ),
        ),
    ]
