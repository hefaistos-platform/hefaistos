import uuid

import django.db.models.deletion
from django.db import migrations, models


def forward_backfill(apps, schema_editor):
    Organization = apps.get_model('organizations', 'Organization')
    SmtpSettings = apps.get_model('organizations', 'SmtpSettings')
    SharedSmtpProfile = apps.get_model('organizations', 'SharedSmtpProfile')
    OrganizationSmtpSettings = apps.get_model('organizations', 'OrganizationSmtpSettings')
    HefaistosInstanceIdentity = apps.get_model('organizations', 'HefaistosInstanceIdentity')

    legacy = SmtpSettings.objects.filter(singleton_key='default').first()
    shared_profile = None
    if legacy and (legacy.smtp_server or '').strip():
        shared_profile, _ = SharedSmtpProfile.objects.get_or_create(
            name='Default Shared SMTP',
            defaults={
                'smtp_server': legacy.smtp_server,
                'smtp_port': legacy.smtp_port,
                'encryption': legacy.encryption,
                'login_method': legacy.login_method,
                'smtp_username': legacy.smtp_username,
                '_smtp_password': getattr(legacy, '_smtp_password', ''),
                'from_email': legacy.from_email,
                'is_active': True,
            },
        )

    for org in Organization.objects.all().order_by('created_at', 'id'):
        defaults = {
            'enforce_shared': False,
            'custom_enabled': False,
        }
        if shared_profile is not None:
            defaults['shared_profile'] = shared_profile
        org_settings, created = OrganizationSmtpSettings.objects.get_or_create(
            organization=org,
            defaults=defaults,
        )
        if not created and shared_profile is not None and org_settings.shared_profile_id is None:
            org_settings.shared_profile = shared_profile
            org_settings.save(update_fields=['shared_profile', 'updated_at'])

    # Preserve any existing global identity row and create per-organization identities.
    for org in Organization.objects.all().order_by('created_at', 'id'):
        exists = HefaistosInstanceIdentity.objects.filter(organization_id=org.id).exists()
        if exists:
            continue

        seed = f"hefaistos-org-identity:{org.id}"
        candidate = uuid.uuid5(uuid.NAMESPACE_DNS, seed)
        salt = 0
        while HefaistosInstanceIdentity.objects.filter(instance_id=candidate).exists():
            salt += 1
            candidate = uuid.uuid5(uuid.NAMESPACE_DNS, f"{seed}:{salt}")

        HefaistosInstanceIdentity.objects.create(
            organization_id=org.id,
            singleton_key=f"org:{org.id}",
            instance_id=candidate,
        )


def noop_reverse(apps, schema_editor):
    # Keep created records intact on rollback to avoid destructive behavior.
    return


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0026_organization_max_users'),
    ]

    operations = [
        migrations.CreateModel(
            name='SharedSmtpProfile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120, unique=True)),
                ('smtp_server', models.CharField(max_length=255)),
                ('smtp_port', models.PositiveIntegerField(default=587)),
                ('encryption', models.CharField(choices=[('NONE', 'None'), ('SSL', 'SSL'), ('STARTTLS', 'STARTTLS')], default='STARTTLS', max_length=16)),
                ('login_method', models.CharField(choices=[('PLAIN', 'PLAIN'), ('LOGIN', 'LOGIN')], default='PLAIN', max_length=16)),
                ('smtp_username', models.CharField(blank=True, default='', max_length=255)),
                ('_smtp_password', models.TextField(blank=True, db_column='smtp_password', default='', help_text='Encrypted SMTP password (do not access directly)')),
                ('from_email', models.EmailField(blank=True, default='', max_length=254)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_shared_smtp_profiles', to='identity.customuser')),
            ],
            options={
                'verbose_name': 'Shared SMTP Profile',
                'verbose_name_plural': 'Shared SMTP Profiles',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='OrganizationSmtpSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enforce_shared', models.BooleanField(default=False, help_text='When enabled, organization admins cannot override with custom SMTP.')),
                ('custom_enabled', models.BooleanField(default=False, help_text='Enable organization-local SMTP configuration.')),
                ('custom_smtp_server', models.CharField(blank=True, default='', max_length=255)),
                ('custom_smtp_port', models.PositiveIntegerField(default=587)),
                ('custom_encryption', models.CharField(choices=[('NONE', 'None'), ('SSL', 'SSL'), ('STARTTLS', 'STARTTLS')], default='STARTTLS', max_length=16)),
                ('custom_login_method', models.CharField(choices=[('PLAIN', 'PLAIN'), ('LOGIN', 'LOGIN')], default='PLAIN', max_length=16)),
                ('custom_smtp_username', models.CharField(blank=True, default='', max_length=255)),
                ('_custom_smtp_password', models.TextField(blank=True, db_column='custom_smtp_password', default='', help_text='Encrypted custom SMTP password (do not access directly)')),
                ('custom_from_email', models.EmailField(blank=True, default='', max_length=254)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='smtp_settings', to='organizations.organization')),
                ('shared_profile', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='organization_assignments', to='organizations.sharedsmtpprofile')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='updated_org_smtp_settings', to='identity.customuser')),
            ],
            options={
                'verbose_name': 'Organization SMTP Settings',
                'verbose_name_plural': 'Organization SMTP Settings',
            },
        ),
        migrations.AddField(
            model_name='hefaistosinstanceidentity',
            name='organization',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='hefaistos_instance_identity', to='organizations.organization'),
        ),
        migrations.AlterField(
            model_name='hefaistosinstanceidentity',
            name='singleton_key',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
        migrations.AlterModelOptions(
            name='hefaistosinstanceidentity',
            options={'verbose_name': 'HEFAISTOS Instance Identity', 'verbose_name_plural': 'HEFAISTOS Instance Identities'},
        ),
        migrations.RunPython(forward_backfill, noop_reverse),
    ]
