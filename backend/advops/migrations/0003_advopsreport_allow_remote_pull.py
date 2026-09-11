from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('advops', '0002_rename_advops_advo_status_priority_idx_advops_advo_status_42fdb1_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='advopsreport',
            name='allow_remote_pull',
            field=models.BooleanField(
                default=False,
                help_text='If enabled, this ADVOPS hunt can be exported to trusted remote HEFAISTOS peers.',
            ),
        ),
    ]
