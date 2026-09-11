from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0022_alter_detectionrule_format_add_eql'),
    ]

    operations = [
        migrations.AddField(
            model_name='rulerepository',
            name='rag_branch',
            field=models.CharField(
                blank=True,
                default='main',
                help_text='Git branch used for RAG dataset sync.',
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name='rulerepository',
            name='rag_dataset_path',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Repository-relative dataset path or glob pattern for JSONL/KQL sources.',
                max_length=500,
            ),
        ),
        migrations.AddField(
            model_name='rulerepository',
            name='rag_last_synced',
            field=models.DateTimeField(
                blank=True,
                help_text='Timestamp of the most recent completed RAG sync attempt.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='rulerepository',
            name='rag_last_synced_templates',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Number of templates synchronized in the latest successful RAG sync.',
            ),
        ),
        migrations.AddField(
            model_name='rulerepository',
            name='rag_last_sync_error',
            field=models.TextField(blank=True, default='', help_text='Last RAG sync error message (if any).'),
        ),
        migrations.AddField(
            model_name='rulerepository',
            name='rag_last_sync_status',
            field=models.CharField(
                blank=True,
                choices=[
                    ('IDLE', 'Idle'),
                    ('QUEUED', 'Queued'),
                    ('RUNNING', 'Running'),
                    ('SUCCESS', 'Success'),
                    ('FAILED', 'Failed'),
                ],
                default='IDLE',
                help_text='Status of the most recent RAG sync lifecycle.',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='rulerepository',
            name='rag_next_scheduled_sync',
            field=models.DateTimeField(
                blank=True,
                help_text='When the next scheduled RAG sync should occur',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='rulerepository',
            name='rag_sync_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Whether RAG template sync from this repository is enabled',
            ),
        ),
        migrations.AddField(
            model_name='rulerepository',
            name='rag_sync_schedule',
            field=models.CharField(
                choices=[
                    ('DISABLED', 'Disabled'),
                    ('24H', 'Every 24 hours'),
                    ('48H', 'Every 48 hours'),
                    ('72H', 'Every 72 hours'),
                    ('WEEKLY', 'Weekly'),
                ],
                default='DISABLED',
                help_text='Schedule for automatic RAG template sync from this repository',
                max_length=20,
            ),
        ),
    ]

