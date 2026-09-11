from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0042_workbench_id_counter'),
    ]

    operations = [
        migrations.AddField(
            model_name='playbookgraph',
            name='allow_remote_pull',
            field=models.BooleanField(
                default=False,
                help_text='If enabled, this workbench can be exported to trusted remote HEFAISTOS peers.',
            ),
        ),
    ]
