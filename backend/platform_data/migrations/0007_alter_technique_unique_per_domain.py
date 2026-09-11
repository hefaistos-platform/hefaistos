# Generated manually for multi-domain technique support
# Removes global unique constraint on technique_id, adds unique per (technique_id, domain)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('platform_data', '0006_alter_mitredetectionstrategy_options'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mitreattacktechnique',
            name='technique_id',
            field=models.CharField(max_length=20),
        ),
        migrations.AddConstraint(
            model_name='mitreattacktechnique',
            constraint=models.UniqueConstraint(fields=['technique_id', 'domain'], name='unique_technique_per_domain'),
        ),
    ]
