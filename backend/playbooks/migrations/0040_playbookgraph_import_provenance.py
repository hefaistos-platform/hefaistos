import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0039_playbookgraph_downstream_correlation_requirements'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='playbookgraph',
            name='imported_from_repo',
            field=models.CharField(blank=True, default='', help_text='GitHub repo (owner/name) this workbench was imported from, e.g. org/rules-prod', max_length=512),
        ),
        migrations.AddField(
            model_name='playbookgraph',
            name='imported_from_commit_sha',
            field=models.CharField(blank=True, default='', help_text='Git commit SHA at which the HEF bundle was read during import', max_length=40),
        ),
        migrations.AddField(
            model_name='playbookgraph',
            name='imported_from_path',
            field=models.CharField(blank=True, default='', help_text='Path of the HEF bundle within the repository (the MDR YAML path)', max_length=512),
        ),
        migrations.AddField(
            model_name='playbookgraph',
            name='imported_at',
            field=models.DateTimeField(blank=True, help_text='Timestamp of the import operation', null=True),
        ),
        migrations.AddField(
            model_name='playbookgraph',
            name='imported_by',
            field=models.ForeignKey(blank=True, help_text='User who triggered the HEF import job', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='imported_workbenches', to=settings.AUTH_USER_MODEL),
        ),
    ]
