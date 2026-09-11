from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0019_alter_customuser_role_add_resource_manager'),
        ('organizations', '0032_organization_workbench_visibility_policy'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrganizationBillingProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stripe_customer_id', models.CharField(blank=True, default='', max_length=120)),
                ('stripe_subscription_id', models.CharField(blank=True, default='', max_length=120)),
                ('included_users', models.PositiveIntegerField(default=1)),
                ('included_organizations', models.PositiveIntegerField(default=1)),
                ('extra_users', models.PositiveIntegerField(default=0)),
                ('extra_organizations', models.PositiveIntegerField(default=0)),
                ('currency', models.CharField(default='EUR', max_length=8)),
                ('last_checkout_session_id', models.CharField(blank=True, default='', max_length=120)),
                ('last_payment_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.OneToOneField(on_delete=models.deletion.CASCADE, related_name='billing_profile', to='organizations.organization')),
            ],
            options={
                'verbose_name': 'Organization Billing Profile',
                'verbose_name_plural': 'Organization Billing Profiles',
            },
        ),
        migrations.CreateModel(
            name='OrganizationManagerAccess',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('access_role', models.CharField(choices=[('OWNER', 'Owner'), ('RESOURCE_MANAGER', 'Resource Manager')], default='RESOURCE_MANAGER', max_length=32)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='created_organization_manager_access', to='identity.customuser')),
                ('organization', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='manager_access', to='organizations.organization')),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='managed_organization_access', to='identity.customuser')),
            ],
            options={
                'verbose_name': 'Organization Manager Access',
                'verbose_name_plural': 'Organization Manager Access',
                'unique_together': {('user', 'organization')},
            },
        ),
    ]
