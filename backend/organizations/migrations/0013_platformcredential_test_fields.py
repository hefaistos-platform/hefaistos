from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0012_platformcredential'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Rename the Python field attribute (db column name stays the same via db_column)
        migrations.RenameField(
            model_name='platformcredential',
            old_name='credentials_json',
            new_name='_credentials_json',
        ),
        migrations.AlterField(
            model_name='platformcredential',
            name='_credentials_json',
            field=models.TextField(
                blank=True,
                db_column='credentials_json',
                default='',
                help_text='Encrypted JSON blob of platform credentials (do not access directly)',
            ),
        ),
        migrations.AddField(
            model_name='platformcredential',
            name='last_tested',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='platformcredential',
            name='test_status',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='platformcredential',
            name='test_message',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='platformcredential',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_platform_credentials',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
