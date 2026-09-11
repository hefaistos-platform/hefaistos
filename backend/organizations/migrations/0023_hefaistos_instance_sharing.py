import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0022_organizationaitaskconfig_and_runs'),
    ]

    operations = [
        migrations.CreateModel(
            name='HefaistosInstanceIdentity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('singleton_key', models.CharField(default='default', max_length=32, unique=True)),
                ('instance_id', models.UUIDField(unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'HEFAISTOS Instance Identity',
                'verbose_name_plural': 'HEFAISTOS Instance Identity',
            },
        ),
        migrations.CreateModel(
            name='HefaistosInboundShareKey',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120)),
                ('key_hash', models.CharField(help_text='SHA-256 hex hash of the raw inbound key.', max_length=64, unique=True)),
                ('key_hint', models.CharField(blank=True, default='', help_text='Non-sensitive key preview for admins (e.g. prefix/suffix).', max_length=24)),
                ('allowed_scopes', models.JSONField(blank=True, default=list, help_text='Allowed pull scopes for this key: WORKBENCH, RULES, ACH, ALL.')),
                ('is_active', models.BooleanField(default=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_hefaistos_inbound_share_keys', to='identity.customuser')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hefaistos_inbound_share_keys', to='organizations.organization')),
            ],
            options={
                'verbose_name': 'HEFAISTOS Inbound Share Key',
                'verbose_name_plural': 'HEFAISTOS Inbound Share Keys',
                'ordering': ['name'],
                'unique_together': {('organization', 'name')},
            },
        ),
        migrations.CreateModel(
            name='HefaistosRemotePeer',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120)),
                ('remote_url', models.URLField(max_length=512)),
                ('remote_instance_id', models.UUIDField()),
                ('_api_key', models.TextField(blank=True, db_column='api_key', default='', help_text='Encrypted API key for remote pull authentication.')),
                ('default_scope', models.CharField(choices=[('WORKBENCH', 'Workbench'), ('RULES', 'Rules'), ('ACH', 'ACH'), ('ALL', 'All')], default='ALL', help_text='Default content range to pull from the remote instance.', max_length=16)),
                ('verify_ssl', models.BooleanField(default=True)),
                ('allow_self_signed', models.BooleanField(default=False)),
                ('tls_cert_fingerprint', models.CharField(blank=True, default='', help_text='Optional SHA-256 TLS certificate fingerprint pin (hex).', max_length=128)),
                ('enabled', models.BooleanField(default=True)),
                ('last_sync_at', models.DateTimeField(blank=True, null=True)),
                ('last_sync_status', models.CharField(blank=True, default='', max_length=16)),
                ('last_sync_message', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_hefaistos_remote_peers', to='identity.customuser')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hefaistos_remote_peers', to='organizations.organization')),
            ],
            options={
                'verbose_name': 'HEFAISTOS Remote Peer',
                'verbose_name_plural': 'HEFAISTOS Remote Peers',
                'ordering': ['name'],
                'unique_together': {('organization', 'name')},
            },
        ),
        migrations.CreateModel(
            name='HefaistosPullJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('requested_scope', models.CharField(choices=[('WORKBENCH', 'Workbench'), ('RULES', 'Rules'), ('ACH', 'ACH'), ('ALL', 'All')], default='ALL', max_length=16)),
                ('status', models.CharField(choices=[('QUEUED', 'Queued'), ('PROCESSING', 'Processing'), ('COMPLETED', 'Completed'), ('FAILED', 'Failed')], default='QUEUED', max_length=16)),
                ('summary', models.JSONField(blank=True, default=dict)),
                ('message', models.TextField(blank=True, default='')),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hefaistos_pull_jobs', to='organizations.organization')),
                ('peer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pull_jobs', to='organizations.hefaistosremotepeer')),
                ('triggered_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='hefaistos_pull_jobs', to='identity.customuser')),
            ],
            options={
                'verbose_name': 'HEFAISTOS Pull Job',
                'verbose_name_plural': 'HEFAISTOS Pull Jobs',
                'ordering': ['-started_at'],
            },
        ),
        migrations.AddIndex(
            model_name='hefaistosinboundsharekey',
            index=models.Index(fields=['organization', 'is_active'], name='organizatio_organiza_8234e6_idx'),
        ),
        migrations.AddIndex(
            model_name='hefaistosinboundsharekey',
            index=models.Index(fields=['key_hash'], name='organizatio_key_has_16e35f_idx'),
        ),
    ]
