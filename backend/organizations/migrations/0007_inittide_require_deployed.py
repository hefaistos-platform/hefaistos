from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0006_playbookcommithistory_deployed_to_siems'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='inittideconfiguration',
            name='require_peer_review',
        ),
        migrations.AddField(
            model_name='inittideconfiguration',
            name='require_deployed',
            field=models.BooleanField(
                default=True,
                help_text='Only allow commits to InitTide when the rule is in DEPLOYED status',
            ),
        ),
        migrations.AddField(
            model_name='inittideconfiguration',
            name='auto_commit_on_status_change',
            field=models.BooleanField(
                default=False,
                help_text='Automatically commit to InitTide when rule status changes to DEPLOYED',
            ),
        ),
    ]
