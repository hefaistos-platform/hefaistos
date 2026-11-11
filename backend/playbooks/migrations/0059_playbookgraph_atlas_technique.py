from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0058_playbookgraph_test_runs'),
        ('platform_data', '0016_atlasimportjob'),
    ]

    operations = [
        migrations.AddField(
            model_name='playbookgraph',
            name='atlas_technique',
            field=models.ForeignKey(
                blank=True,
                help_text='Selected MITRE ATLAS technique for this workbench.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='playbook_graphs',
                to='platform_data.atlastechnique',
            ),
        ),
    ]
