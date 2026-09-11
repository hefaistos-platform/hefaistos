# Generated manually for linking DetectionRule to PlaybookGraph
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0004_alter_rulerepository_options_and_more'),
        ('playbooks', '0027_merge_test_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='detectionrule',
            name='playbook',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='linked_rule', to='playbooks.playbookgraph'),
        ),
    ]
