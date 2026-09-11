from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0023_rulerepository_rag_sync_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='RuleRepositoryRAGFileStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_path', models.CharField(max_length=500)),
                ('source_branch', models.CharField(blank=True, default='main', max_length=128)),
                ('language', models.CharField(default='KQL', max_length=16)),
                ('ingestion_status', models.CharField(choices=[('INGESTED', 'Ingested'), ('FAILED', 'Failed')], default='FAILED', max_length=16)),
                ('templates_count', models.PositiveIntegerField(default=0)),
                ('last_synced_at', models.DateTimeField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True, default='')),
                ('used_in_generation', models.BooleanField(default=False)),
                ('usage_count', models.PositiveIntegerField(default=0)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('repository', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='rag_files', to='rules.rulerepository')),
            ],
            options={
                'verbose_name': 'RAG File Status',
                'verbose_name_plural': 'RAG File Statuses',
                'ordering': ['source_path'],
                'unique_together': {('repository', 'source_path', 'source_branch', 'language')},
            },
        ),
    ]

