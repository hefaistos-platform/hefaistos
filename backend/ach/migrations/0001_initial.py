# Generated manually for ACH app initial migration with status support
from django.db import migrations, models
import django.db.models.deletion
import uuid
from django.conf import settings

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('data_catalog', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ACHTemplate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('hypotheses', models.JSONField(default=list, help_text="List of hypothesis strings")),
                ('evidence', models.JSONField(default=list, help_text="List of evidence objects {'content': '...', 'credibility': '...'}")),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='ACHAnalysis',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('RESEARCH', 'Research'), ('FINISHED', 'Finished')], default='RESEARCH', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ach_analyses', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'ACH Analyses',
            },
        ),
        migrations.CreateModel(
            name='Hypothesis',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField()),
                ('is_proven', models.BooleanField(default=False)),
                ('sequence', models.IntegerField(default=0)),
                ('analysis', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hypotheses', to='ach.achanalysis')),
            ],
            options={
                'ordering': ['sequence'],
            },
        ),
        migrations.CreateModel(
            name='Evidence',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField()),
                ('credibility', models.CharField(choices=[('HIGH', 'High'), ('MEDIUM', 'Medium'), ('LOW', 'Low')], default='MEDIUM', max_length=10)),
                ('relevance', models.TextField(blank=True)),
                ('sequence', models.IntegerField(default=0)),
                ('log_reference', models.CharField(blank=True, help_text='Specific Log ID or Query', max_length=255)),
                ('analysis', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='evidence_items', to='ach.achanalysis')),
                ('data_source', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ach_evidence', to='data_catalog.datasource')),
            ],
            options={
                'ordering': ['sequence'],
            },
        ),
        migrations.CreateModel(
            name='MatrixCell',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('score', models.CharField(choices=[('CC', 'Very Consistent'), ('C', 'Consistent'), ('N', 'Neutral'), ('I', 'Inconsistent'), ('II', 'Very Inconsistent')], default='N', max_length=2)),
                ('notes', models.TextField(blank=True)),
                ('evidence', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='matrix_cells', to='ach.evidence')),
                ('hypothesis', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='matrix_cells', to='ach.hypothesis')),
            ],
            options={
                'unique_together': {('hypothesis', 'evidence')},
            },
        ),
    ]
