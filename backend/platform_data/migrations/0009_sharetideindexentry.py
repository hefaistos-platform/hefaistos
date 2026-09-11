import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('platform_data', '0008_d3fend_models'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShareTideIndexEntry',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('category', models.CharField(
                    db_index=True,
                    help_text="Vocabulary category, e.g. 'bdr_platforms', 'mdr_responders'.",
                    max_length=100,
                )),
                ('value', models.CharField(
                    help_text="Vocabulary entry value, e.g. 'Windows', 'High'.",
                    max_length=255,
                )),
                ('description', models.TextField(
                    blank=True,
                    help_text='Optional description or notes for this vocabulary entry.',
                )),
                ('source_url', models.URLField(
                    blank=True,
                    help_text='URL to the upstream ShareTide index file.',
                    max_length=512,
                )),
                ('sort_order', models.PositiveSmallIntegerField(
                    default=0,
                    help_text='Display ordering within category.',
                )),
            ],
            options={
                'verbose_name': 'ShareTide Index Entry',
                'verbose_name_plural': 'ShareTide Index Entries',
                'ordering': ['category', 'sort_order', 'value'],
            },
        ),
        migrations.AddConstraint(
            model_name='sharetideindexentry',
            constraint=models.UniqueConstraint(
                fields=['category', 'value'],
                name='unique_sharetide_category_value',
            ),
        ),
    ]
