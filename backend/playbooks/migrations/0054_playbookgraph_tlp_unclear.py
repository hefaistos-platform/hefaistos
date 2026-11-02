from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('playbooks', '0053_playbookgraph_detection_rule_format'),
    ]

    operations = [
        migrations.AlterField(
            model_name='playbookgraph',
            name='tlp_classification',
            field=models.CharField(
                choices=[
                    ('CLEAR', 'TLP:CLEAR - Public disclosure'),
                    ('GREEN', 'TLP:GREEN - Community sharing'),
                    ('AMBER', 'TLP:AMBER - Limited disclosure'),
                    ('AMBER+STRICT', 'TLP:AMBER+STRICT - Organization only'),
                    ('RED', 'TLP:RED - Personal for named recipients'),
                    ('UNCLEAR', 'TLP:UNCLEAR - Source or sharing model unknown, unclear, or not used (tlp-unclear.org)'),
                ],
                default='UNCLEAR',
                help_text='Traffic Light Protocol classification for information sharing; UNCLEAR follows the community proposal at https://tlp-unclear.org/',
                max_length=20,
            ),
        ),
    ]
