from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0016_authprovidersettings_organization'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='session_timeout_hours',
            field=models.PositiveSmallIntegerField(
                choices=[(2, '2 hours'), (4, '4 hours'), (8, '8 hours'), (12, '12 hours'), (24, '24 hours')],
                default=4,
                help_text='Auto-logout timeout after this many hours of inactivity.',
            ),
        ),
    ]
