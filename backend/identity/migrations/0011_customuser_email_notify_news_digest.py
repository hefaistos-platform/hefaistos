from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0010_uncheck_all_email_notifications'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='email_notify_news_digest',
            field=models.BooleanField(default=False, help_text='Email me when there is a news digest'),
        ),
    ]
