from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0025_hefaistos_remote_pull_policy'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='max_users',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Maximum users allowed in this organization. Leave empty for unlimited.',
                null=True,
                validators=[MinValueValidator(1)],
            ),
        ),
    ]
