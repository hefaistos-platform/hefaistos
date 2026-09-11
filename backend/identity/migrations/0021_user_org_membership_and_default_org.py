from django.db import migrations, models
import django.db.models.deletion


def seed_user_org_memberships(apps, schema_editor):
    CustomUser = apps.get_model('identity', 'CustomUser')
    UserOrganizationMembership = apps.get_model('identity', 'UserOrganizationMembership')

    for user in CustomUser.objects.exclude(organization__isnull=True).iterator():
        UserOrganizationMembership.objects.get_or_create(
            user_id=user.id,
            organization_id=user.organization_id,
        )
        if not user.default_organization_id:
            user.default_organization_id = user.organization_id
            user.save(update_fields=['default_organization'])


def reverse_seed_user_org_memberships(apps, schema_editor):
    UserOrganizationMembership = apps.get_model('identity', 'UserOrganizationMembership')
    UserOrganizationMembership.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0033_billing_profile_and_manager_access'),
        ('identity', '0020_authprovidersettings_oidc_tls'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='default_organization',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='default_users', to='organizations.organization'),
        ),
        migrations.CreateModel(
            name='UserOrganizationMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_memberships', to='organizations.organization')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='organization_memberships', to='identity.customuser')),
            ],
            options={
                'ordering': ['organization__name'],
                'unique_together': {('user', 'organization')},
            },
        ),
        migrations.RunPython(seed_user_org_memberships, reverse_seed_user_org_memberships),
    ]
