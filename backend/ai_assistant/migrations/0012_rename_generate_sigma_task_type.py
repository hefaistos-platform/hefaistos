"""
Rename AIGenerationTask.TaskType.GENERATE_SIGMA → GENERATE_RULE.

All existing rows with task_type='GENERATE_SIGMA' are updated to
'GENERATE_RULE' so they continue to work after the code rename.
"""
from django.db import migrations


def rename_task_type_forward(apps, schema_editor):
    AIGenerationTask = apps.get_model('ai_assistant', 'AIGenerationTask')
    AIGenerationTask.objects.filter(task_type='GENERATE_SIGMA').update(task_type='GENERATE_RULE')


def rename_task_type_backward(apps, schema_editor):
    AIGenerationTask = apps.get_model('ai_assistant', 'AIGenerationTask')
    AIGenerationTask.objects.filter(task_type='GENERATE_RULE').update(task_type='GENERATE_SIGMA')


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0011_ai_generation_task'),
    ]

    operations = [
        migrations.RunPython(rename_task_type_forward, rename_task_type_backward),
    ]
