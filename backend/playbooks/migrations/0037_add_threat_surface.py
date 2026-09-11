from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0036_add_opentide_v2_1_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='playbookgraph',
            name='threat_surface',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Manually specified threat surface categories (e.g. OS::Windows, Cloud::Azure)',
            ),
        ),
    ]
