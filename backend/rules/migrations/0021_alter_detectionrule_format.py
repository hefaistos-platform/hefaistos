from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rules", "0020_rulerepository_verify_ssl"),
    ]

    operations = [
        migrations.AlterField(
            model_name="detectionrule",
            name="format",
            field=models.CharField(
                choices=[
                    ("KQL", "Kusto Query Language"),
                    ("WAZUH", "Wazuh XML"),
                    ("SPL", "Splunk SPL"),
                    ("AQL", "IBM QRadar AQL"),
                    ("OPENTIDE", "OpenTide Multi-Platform"),
                    ("OTHER", "Other"),
                ],
                default="KQL",
                max_length=10,
            ),
        ),
    ]
