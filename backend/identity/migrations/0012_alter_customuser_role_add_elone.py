from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0011_customuser_email_notify_news_digest'),
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
                ],
                default='ANALYST',
                help_text="The user's role, which determines their permissions.",
                max_length=10,
            ),
        ),
    ]
