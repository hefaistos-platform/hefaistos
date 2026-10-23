from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('rules', '0028_detectionrule_custom_file_extension'),
                    ('playbooks', '0053_playbookgraph_detection_rule_format')]
    operations = [
        migrations.AddField(model_name='detectionrule', name='authoring_document', field=models.JSONField(blank=True, null=True)),
        migrations.AddField(model_name='detectionrule', name='attached_workbench', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='attached_rules', to='playbooks.playbookgraph')),
    ]
