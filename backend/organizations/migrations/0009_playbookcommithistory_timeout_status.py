from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0008_playbookcommithistory_committed_file_paths'),
    ]

    operations = [
        migrations.AlterField(
            model_name='playbookcommithistory',
            name='deployment_status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'),
                    ('DEPLOYED', 'Deployed'),
                    ('FAILED', 'Failed'),
                    ('TIMEOUT', 'Timed Out'),
                ],
                default='PENDING',
                max_length=20,
            ),
        ),
    ]
