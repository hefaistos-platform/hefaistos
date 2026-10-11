from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('playbooks', '0051_capabilityabstraction_column'),
    ]

    operations = [
        migrations.AddField(
            model_name='capabilityabstraction',
            name='allow_remote_pull',
            field=models.BooleanField(
                default=False,
                help_text='Allow approved organization-scoped entries to be pulled by remote HEFAISTOS instances.',
            ),
        ),
    ]
