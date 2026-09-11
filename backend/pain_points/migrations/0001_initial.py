# Generated migration for Pain Points feature

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('organizations', '0003_organization_entity'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PainPoint',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('subject', models.CharField(help_text='Short description of the pain point (max 80 characters)', max_length=80)),
                ('description', models.TextField(help_text='Detailed description of the issue, idea, or complaint', max_length=2000)),
                ('priority', models.CharField(choices=[('LOW', 'Low'), ('MEDIUM', 'Medium'), ('HIGH', 'High')], default='MEDIUM', help_text='Priority level: Low, Medium, or High', max_length=10)),
                ('status', models.CharField(choices=[('OPEN', 'Open'), ('IN_PROGRESS', 'In Progress'), ('SOLVED', 'Solved'), ('CLOSED', 'Closed'), ('ARCHIVED', 'Archived')], default='OPEN', help_text='Current status of the pain point', max_length=15)),
                ('resolved_at', models.DateTimeField(blank=True, help_text='Timestamp when the pain point was solved/closed', null=True)),
                ('resolution_notes', models.TextField(blank=True, help_text='Admin notes on how the pain point was addressed', max_length=1000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('author', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pain_points_created', to=settings.AUTH_USER_MODEL)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pain_points', to='organizations.organization')),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pain_points_resolved', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PainPointComment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('content', models.TextField(max_length=1000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('author', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pain_point_comments', to=settings.AUTH_USER_MODEL)),
                ('pain_point', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comments', to='pain_points.painpoint')),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='painpoint',
            index=models.Index(fields=['organization', 'status'], name='pain_points_organiza_idx'),
        ),
        migrations.AddIndex(
            model_name='painpoint',
            index=models.Index(fields=['priority', 'status'], name='pain_points_priorit_idx'),
        ),
        migrations.AddIndex(
            model_name='painpoint',
            index=models.Index(fields=['author'], name='pain_points_author_idx'),
        ),
        migrations.AddIndex(
            model_name='painpointcomment',
            index=models.Index(fields=['pain_point'], name='pain_points_pain_po_idx'),
        ),
        migrations.AddIndex(
            model_name='painpointcomment',
            index=models.Index(fields=['author'], name='pain_points_author_7f90c0_idx'),
        ),
    ]
