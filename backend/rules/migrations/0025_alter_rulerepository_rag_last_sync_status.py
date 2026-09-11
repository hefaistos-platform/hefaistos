from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0024_rulerepositoryragfilestatus'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rulerepository',
            name='rag_last_sync_status',
            field=models.CharField(
                blank=True,
                choices=[
                    ('IDLE', 'Idle'),
                    ('QUEUED', 'Queued'),
                    ('RUNNING', 'Running'),
                    ('PARTIAL', 'Partial'),
                    ('SUCCESS', 'Success'),
                    ('FAILED', 'Failed'),
                ],
                default='IDLE',
                help_text='Status of the most recent RAG sync lifecycle.',
                max_length=16,
            ),
        ),
    ]

