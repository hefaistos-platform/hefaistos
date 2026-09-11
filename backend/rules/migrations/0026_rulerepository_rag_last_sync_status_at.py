from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0025_alter_rulerepository_rag_last_sync_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='rulerepository',
            name='rag_last_sync_status_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Timestamp when rag_last_sync_status was last updated.',
                null=True,
            ),
        ),
    ]
