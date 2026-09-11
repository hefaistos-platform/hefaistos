from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0038_playbookgraph_detection_focus_layer_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='playbookgraph',
            name='downstream_correlation_requirements',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Temporal/join logic for multi-event correlation detections. Structure: { correlationScope, temporalLogic, joinKeys, stateManagement, falsePositiveMitigation }',
            ),
        ),
    ]
