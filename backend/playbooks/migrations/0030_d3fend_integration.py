# Generated for D3FEND framework integration
# Adds D3FEND technique mappings to PlaybookGraph and PlaybookNode

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0029_add_maieutic_fields'),
        ('platform_data', '0008_d3fend_models'),
    ]

    operations = [
        # Add d3fend_techniques to PlaybookGraph
        migrations.AddField(
            model_name='playbookgraph',
            name='d3fend_techniques',
            field=models.ManyToManyField(
                blank=True,
                help_text='D3FEND techniques this detection implements',
                related_name='implementing_playbooks',
                to='platform_data.d3fenddefensivetechnique'
            ),
        ),
        # Add d3fend_mappings to PlaybookNode
        migrations.AddField(
            model_name='playbooknode',
            name='d3fend_mappings',
            field=models.ManyToManyField(
                blank=True,
                related_name='nodes',
                to='platform_data.d3fenddefensivetechnique'
            ),
        ),
    ]
