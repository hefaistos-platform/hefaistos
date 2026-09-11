import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0040_playbookgraph_import_provenance'),
    ]

    operations = [
        migrations.CreateModel(
            name='L1PortalEntry',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=300)),
                ('url_token', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('response_playbook', models.TextField(blank=True, default='')),
                ('known_false_positives', models.TextField(blank=True, default='')),
                ('blind_spots_coverage_gaps', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('graph', models.OneToOneField(on_delete=models.deletion.CASCADE, related_name='l1_portal_entry', to='playbooks.playbookgraph')),
                ('organization', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='l1_portal_entries', to='organizations.organization')),
            ],
            options={
                'ordering': ['-updated_at'],
                'indexes': [
                    models.Index(fields=['organization', 'updated_at'], name='playbooks_l1_organiz_7de8ec_idx'),
                    models.Index(fields=['url_token'], name='playbooks_l1_url_tok_b4d8d6_idx'),
                ],
            },
        ),
    ]
