from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0013_accountsetuptoken'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('ADMIN', 'Admin'),
                    ('ANALYST', 'Analyst'),
                    ('REVIEWER', 'Reviewer'),
                    ('VIEWER', 'Viewer'),
                    ('ELONE', 'ElOne'),
                    ('BOT_AUDITOR_ORG', 'Bot Auditor (Org)'),
                    ('BOT_AUDITOR_GLOBAL', 'Bot Auditor (Global)'),
                ],
                default='ANALYST',
                help_text="The user's role, which determines their permissions.",
                max_length=24,
            ),
        ),
    ]
