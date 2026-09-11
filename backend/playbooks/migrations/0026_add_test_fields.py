from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0025_merge_conflict_false_positive_rate'),
    ]

    operations = [
        migrations.AddField(
            model_name='playbookgraph',
            name='test_scenario',
            field=models.TextField(blank=True, help_text='Markdown description of how to simulate this attack.'),
        ),
        migrations.AddField(
            model_name='playbookgraph',
            name='test_expected_output',
            field=models.TextField(blank=True, help_text='Example log event or artifact created by the test.'),
        ),
    ]
