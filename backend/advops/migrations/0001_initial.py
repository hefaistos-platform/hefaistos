from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('organizations', '0004_mispinstance'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ADVOPSReport',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('hunt_id', models.CharField(max_length=64, unique=True)),
                ('hypothesis', models.TextField(blank=True)),
                ('status', models.CharField(
                    choices=[
                        ('IDEA', 'Idea/Hypothesis'),
                        ('RESEARCH', 'In Research'),
                        ('DEVELOPMENT', 'In Development'),
                        ('APPROVED', 'Approved'),
                        ('TESTING', 'Testing'),
                        ('DEPLOYED', 'Deployed'),
                        ('TUNING', 'Tuning/Maintenance'),
                    ],
                    default='IDEA',
                    max_length=24,
                )),
                ('priority', models.CharField(
                    choices=[
                        ('CRITICAL', 'Critical'),
                        ('HIGH', 'High'),
                        ('MEDIUM', 'Medium'),
                        ('LOW', 'Low'),
                    ],
                    default='MEDIUM',
                    max_length=16,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('verification_summary', models.TextField(blank=True)),
                ('infrastructure_summary', models.TextField(blank=True)),
                ('pivot_summary', models.TextField(blank=True)),
                ('false_positive_summary', models.TextField(blank=True)),
                ('mitre_summary', models.TextField(blank=True)),
                ('detection_logic_summary', models.TextField(blank=True)),
                ('author', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='advops_reports',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='advops_reports',
                    to='organizations.organization',
                )),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='advopsreport',
            index=models.Index(fields=['status', 'priority'], name='advops_advo_status_priority_idx'),
        ),
    ]
