from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0030_d3fend_integration'),
    ]

    operations = [
        migrations.AddField(
            model_name='playbookgraph',
            name='minor_version',
            field=models.IntegerField(default=0),
        ),
    ]
