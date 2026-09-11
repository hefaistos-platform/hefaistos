from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0014_alter_customuser_role_add_bot_auditors'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuthProviderSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('singleton_key', models.CharField(default='default', max_length=32, unique=True)),
                ('auth_mode', models.CharField(choices=[('ENTRA_ONLY', 'Entra only'), ('OIDC_ONLY', 'Generic OIDC only'), ('ENTRA_AND_OIDC', 'Entra + Generic OIDC'), ('ENTRA_AND_LOCAL_BREAKGLASS', 'Entra + Local Break-glass')], default='ENTRA_AND_LOCAL_BREAKGLASS', max_length=40)),
                ('default_login_provider', models.CharField(choices=[('ENTRA', 'Entra'), ('OIDC', 'Generic OIDC'), ('LOCAL', 'Local')], default='ENTRA', max_length=16)),
                ('enable_entra', models.BooleanField(default=False)),
                ('enable_oidc', models.BooleanField(default=False)),
                ('allow_local_breakglass', models.BooleanField(default=True)),
                ('auto_provision_users', models.BooleanField(default=True)),
                ('sync_claims_on_login', models.BooleanField(default=True)),
                ('enforce_local_mfa', models.BooleanField(default=True)),
                ('breakglass_usernames', models.TextField(blank=True, default='admin', help_text='Comma separated usernames allowed for local emergency login.')),
                ('entra_tenant_id', models.CharField(blank=True, default='', max_length=255)),
                ('entra_client_id', models.CharField(blank=True, default='', max_length=255)),
                ('_entra_client_secret', models.TextField(blank=True, db_column='entra_client_secret', default='')),
                ('entra_redirect_uri', models.CharField(blank=True, default='', max_length=512)),
                ('entra_scopes', models.CharField(blank=True, default='openid profile email', max_length=512)),
                ('entra_email_claim', models.CharField(blank=True, default='preferred_username', max_length=128)),
                ('entra_username_claim', models.CharField(blank=True, default='preferred_username', max_length=128)),
                ('entra_role_claim', models.CharField(blank=True, default='roles', max_length=128)),
                ('oidc_issuer_url', models.CharField(blank=True, default='', max_length=512)),
                ('oidc_client_id', models.CharField(blank=True, default='', max_length=255)),
                ('_oidc_client_secret', models.TextField(blank=True, db_column='oidc_client_secret', default='')),
                ('oidc_redirect_uri', models.CharField(blank=True, default='', max_length=512)),
                ('oidc_scopes', models.CharField(blank=True, default='openid profile email', max_length=512)),
                ('oidc_email_claim', models.CharField(blank=True, default='email', max_length=128)),
                ('oidc_username_claim', models.CharField(blank=True, default='preferred_username', max_length=128)),
                ('oidc_role_claim', models.CharField(blank=True, default='roles', max_length=128)),
                ('role_admin_values', models.TextField(blank=True, default='HEF-Admins,Admin,ADMIN')),
                ('role_analyst_values', models.TextField(blank=True, default='HEF-Analysts,Analyst,ANALYST')),
                ('role_reviewer_values', models.TextField(blank=True, default='HEF-Reviewers,Reviewer,REVIEWER')),
                ('default_provisioned_role', models.CharField(choices=[('ADMIN', 'Admin'), ('ANALYST', 'Analyst'), ('REVIEWER', 'Reviewer'), ('VIEWER', 'Viewer'), ('ELONE', 'ElOne'), ('BOT_AUDITOR_ORG', 'Bot Auditor (Org)'), ('BOT_AUDITOR_GLOBAL', 'Bot Auditor (Global)')], default='VIEWER', max_length=24)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Authentication Provider Settings',
                'verbose_name_plural': 'Authentication Provider Settings',
            },
        ),
    ]
