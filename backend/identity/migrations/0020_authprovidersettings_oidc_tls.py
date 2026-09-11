from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0019_alter_customuser_role_add_resource_manager'),
    ]

    operations = [
        migrations.AddField(
            model_name='authprovidersettings',
            name='oidc_ca_certificate',
            field=models.TextField(blank=True, default='', help_text='Optional PEM CA certificate used to verify OIDC TLS.'),
        ),
        migrations.AddField(
            model_name='authprovidersettings',
            name='oidc_verify_ssl',
            field=models.BooleanField(default=True, help_text='Verify TLS certificates for OIDC discovery/token/JWKS requests.'),
        ),
    ]
