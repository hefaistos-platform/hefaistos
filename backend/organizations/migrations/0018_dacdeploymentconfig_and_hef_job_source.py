import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0018_autocompleteevent_and_more'),
        ('organizations', '0017_remove_legacy_opentide_models'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DacDeploymentConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mode', models.CharField(choices=[('NONE', 'Do nothing'), ('GIT_PUSH', 'Generate and push to GitHub'), ('GIT_PUSH_AND_DEPLOY', 'Generate, push, and deploy')], default='NONE', max_length=32)),
                ('target_branch', models.CharField(default='main', max_length=255)),
                ('target_folder', models.CharField(blank=True, default='', max_length=255)),
                ('target_platforms', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='dac_deployment_config', to='organizations.organization')),
                ('publish_profile', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dac_deployment_configs', to='organizations.opentidepublishprofile')),
                ('target_repository', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dac_deployment_configs', to='rules.rulerepository')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='updated_dac_deployment_configs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'DaC Deployment Configuration',
                'verbose_name_plural': 'DaC Deployment Configurations',
            },
        ),
        migrations.AddField(
            model_name='opentidehefpublishjob',
            name='source',
            field=models.CharField(choices=[('MANUAL', 'Manual'), ('DAC_AUTOMATION', 'DaC Automation')], default='MANUAL', max_length=20),
        ),
        migrations.AddField(
            model_name='opentidehefpublishjob',
            name='source_graph_minor_version',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='opentidehefpublishjob',
            name='source_graph_version',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
