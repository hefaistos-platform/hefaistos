from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("playbooks", "0046_mve_vnext_foundation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mvedraft",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("MODELED", "Modeled"),
                    ("GENERATION_READY", "Generation Ready"),
                    ("VALIDATED", "Validated"),
                    ("EXPORTED", "Exported"),
                ],
                default="DRAFT",
                max_length=20,
            ),
        ),
    ]
