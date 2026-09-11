from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0031_alter_platformcredential_options_and_more'),
        ('identity', '0015_authprovidersettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='authprovidersettings',
            name='organization',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='auth_settings', to='organizations.organization'),
        ),
    ]
