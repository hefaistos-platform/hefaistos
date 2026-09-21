from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0022_personal_api_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='authprovidersettings',
            name='auth_mode',
            field=models.CharField(
                choices=[
                    ('ENTRA_ONLY', 'Entra only'),
                    ('OIDC_ONLY', 'Generic OIDC only'),
                    ('ENTRA_AND_OIDC', 'Entra + Generic OIDC'),
                    ('ENTRA_AND_LOCAL_BREAKGLASS', 'Entra + Local Break-glass'),
                    ('OIDC_AND_LOCAL_BREAKGLASS', 'Generic OIDC + Local Break-glass'),
                ],
                default='ENTRA_AND_LOCAL_BREAKGLASS',
                max_length=40,
            ),
        ),
    ]
