from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0019_opentidehefimportjob'),
    ]

    operations = [
        migrations.CreateModel(
            name='SmtpSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('singleton_key', models.CharField(default='default', max_length=32, unique=True)),
                ('smtp_server', models.CharField(max_length=255)),
                ('smtp_port', models.PositiveIntegerField(default=587)),
                ('encryption', models.CharField(choices=[('NONE', 'None'), ('SSL', 'SSL'), ('STARTTLS', 'STARTTLS')], default='STARTTLS', max_length=16)),
                ('login_method', models.CharField(choices=[('PLAIN', 'PLAIN'), ('LOGIN', 'LOGIN')], default='PLAIN', max_length=16)),
                ('smtp_username', models.CharField(blank=True, default='', max_length=255)),
                ('_smtp_password', models.TextField(blank=True, db_column='smtp_password', default='', help_text='Encrypted SMTP password (do not access directly)')),
                ('from_email', models.EmailField(blank=True, default='', max_length=254)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'SMTP Settings',
                'verbose_name_plural': 'SMTP Settings',
            },
        ),
    ]
