# Generated migration for autocomplete caching models

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0012_rulerepository_auto_pull_enabled_and_more'),
        ('data_catalog', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SigmaKeyword',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('keyword', models.CharField(db_index=True, max_length=100, unique=True)),
                ('category', models.CharField(db_index=True, max_length=50)),
                ('documentation', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name_plural': 'SIGMA Keywords',
                'ordering': ['category', 'keyword'],
            },
        ),
        migrations.CreateModel(
            name='KQLTable',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('table_name', models.CharField(db_index=True, max_length=100, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'KQL Table',
                'verbose_name_plural': 'KQL Tables',
                'ordering': ['table_name'],
            },
        ),
        migrations.CreateModel(
            name='KQLField',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('field_name', models.CharField(db_index=True, max_length=100)),
                ('field_type', models.CharField(blank=True, max_length=50, null=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('table', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fields', to='rules.kqltable')),
            ],
            options={
                'verbose_name': 'KQL Field',
                'verbose_name_plural': 'KQL Fields',
                'ordering': ['table', 'field_name'],
            },
        ),
        migrations.CreateModel(
            name='FieldMapping',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sigma_field', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                ('kql_field', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                ('mapping_type', models.CharField(choices=[('direct', 'Direct 1:1 mapping'), ('derived', 'Derived/calculated field'), ('unsupported', 'Not available in target format')], default='direct', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('data_source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='field_mappings', to='data_catalog.datasource')),
            ],
            options={
                'verbose_name': 'Field Mapping',
                'verbose_name_plural': 'Field Mappings',
                'ordering': ['data_source', 'sigma_field'],
            },
        ),
        migrations.AddConstraint(
            model_name='kqlfield',
            constraint=models.UniqueConstraint(fields=('table', 'field_name'), name='unique_kql_table_field'),
        ),
        migrations.AddConstraint(
            model_name='fieldmapping',
            constraint=models.UniqueConstraint(fields=('data_source', 'sigma_field', 'kql_field'), name='unique_field_mapping'),
        ),
    ]
