from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('ach', '0003_add_approval_fields'),
        ('platform_data', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='hypothesis',
            name='mitre_technique',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ach_hypotheses',
                to='platform_data.mitreattacktechnique'
            ),
        ),
        # saved_as_template already added by 0003_add_approval_fields or 0004_saved_as_template
    ]
