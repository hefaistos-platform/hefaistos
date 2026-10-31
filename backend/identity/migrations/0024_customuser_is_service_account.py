from django.db import migrations, models


def flag_known_service_accounts(apps, schema_editor):
    """Set the explicit service-account flag for the built-in connector user.

    Historically service accounts were identified by a 'service' substring in
    the username, which allowed privilege escalation. We now rely on an
    explicit flag and only trust the well-known 'connector_svc' account here.
    """
    CustomUser = apps.get_model('identity', 'CustomUser')
    CustomUser.objects.filter(username='connector_svc').update(is_service_account=True)


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0023_authprovidersettings_oidc_breakglass_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='is_service_account',
            field=models.BooleanField(
                default=False,
                help_text='Internal service/connector account that bypasses role-gated mutations.',
            ),
        ),
        migrations.RunPython(flag_known_service_accounts, migrations.RunPython.noop),
    ]
