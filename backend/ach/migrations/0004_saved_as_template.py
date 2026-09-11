from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ach', '0003_hypothesis_mitre_and_saved_template'),
    ]

    operations = [
        migrations.AddField(
            model_name='achanalysis',
            name='saved_as_template',
            field=models.BooleanField(default=False, help_text='Whether this analysis has been saved as a template'),
        ),
    ]
