from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0020_smtpsettings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dacdeploymentconfig',
            name='mode',
            field=models.CharField(
                choices=[
                    ('NONE', 'Do nothing'),
                    ('GIT_PUSH', 'Generate and push to GitHub'),
                    ('GIT_PUSH_AND_DEPLOY', 'Generate, push, and deploy'),
                    ('DEPLOY_ONLY', 'Just push rule to target platform'),
                ],
                default='NONE',
                max_length=32,
            ),
        ),
    ]
