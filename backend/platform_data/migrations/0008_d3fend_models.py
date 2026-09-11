# Generated for D3FEND framework integration
# Adds D3fendDefensiveTechnique, D3fendDigitalArtifact, and D3fendAttackMapping models

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('platform_data', '0007_alter_technique_unique_per_domain'),
    ]

    operations = [
        # Create D3fendDefensiveTechnique model
        migrations.CreateModel(
            name='D3fendDefensiveTechnique',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('d3fend_id', models.CharField(max_length=20, unique=True)),
                ('name', models.CharField(max_length=255)),
                ('definition', models.TextField(blank=True)),
                ('iri', models.URLField(blank=True, max_length=512)),
                ('tactic', models.CharField(blank=True, max_length=100)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='platform_data.d3fenddefensivetechnique')),
            ],
            options={
                'ordering': ['d3fend_id'],
            },
        ),
        # Create D3fendDigitalArtifact model
        migrations.CreateModel(
            name='D3fendDigitalArtifact',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('artifact_id', models.CharField(max_length=100, unique=True)),
                ('name', models.CharField(max_length=255)),
                ('definition', models.TextField(blank=True)),
                ('iri', models.URLField(blank=True, max_length=512)),
                ('techniques', models.ManyToManyField(blank=True, related_name='digital_artifacts', to='platform_data.d3fenddefensivetechnique')),
            ],
        ),
        # Create D3fendAttackMapping model
        migrations.CreateModel(
            name='D3fendAttackMapping',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('relationship', models.CharField(default='counters', max_length=50)),
                ('attack_technique', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='d3fend_countermeasures', to='platform_data.mitreattacktechnique')),
                ('d3fend_technique', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='countered_attacks', to='platform_data.d3fenddefensivetechnique')),
            ],
        ),
        # Add unique constraint
        migrations.AlterUniqueTogether(
            name='d3fendattackmapping',
            unique_together={('attack_technique', 'd3fend_technique')},
        ),
    ]
