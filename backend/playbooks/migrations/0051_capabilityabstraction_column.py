from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0050_telemetry_tagging'),
    ]

    operations = [
        migrations.AddField(
            model_name='capabilityabstraction',
            name='column',
            field=models.CharField(
                blank=True,
                choices=[
                    ('A', 'Column A: Application'),
                    ('U', 'Column U: User-Mode'),
                    ('K', 'Column K: Kernel-Mode'),
                    ('P', 'Column P: Payload Visibility'),
                    ('H', 'Column H: Header Visibility'),
                ],
                default='',
                max_length=1,
            ),
        ),
    ]
