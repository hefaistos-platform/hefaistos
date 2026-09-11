from django.db import migrations, models


def set_default_profile_for_existing_rows(apps, schema_editor):
    PlatformCredential = apps.get_model('organizations', 'PlatformCredential')
    for row in PlatformCredential.objects.all().iterator():
        updates = {}
        if not getattr(row, 'profile_name', None):
            updates['profile_name'] = 'default'
        # Legacy data had one row per org+platform; mark as default.
        if not getattr(row, 'is_default', False):
            updates['is_default'] = True
        if updates:
            PlatformCredential.objects.filter(pk=row.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0027_multitenant_smtp_and_org_identity'),
    ]

    operations = [
        migrations.AddField(
            model_name='platformcredential',
            name='profile_name',
            field=models.CharField(
                default='default',
                help_text='Credential profile name (for example: default, prod-eu, soc-lab).',
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name='platformcredential',
            name='is_default',
            field=models.BooleanField(
                default=False,
                help_text='When enabled, this profile is preferred for deployments when no profile is explicitly selected.',
            ),
        ),
        migrations.RunPython(
            set_default_profile_for_existing_rows,
            migrations.RunPython.noop,
        ),
        migrations.AlterUniqueTogether(
            name='platformcredential',
            unique_together={('organization', 'platform', 'profile_name')},
        ),
    ]
