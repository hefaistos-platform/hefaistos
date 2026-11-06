from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0057_playbookgraph_negative_tests'),
    ]

    operations = [
        migrations.AddField(
            model_name='playbookgraph',
            name='test_runs',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
