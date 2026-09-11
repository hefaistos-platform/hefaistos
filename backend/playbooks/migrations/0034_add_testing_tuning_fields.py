from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0033_playbookgraph_opentide_ai_enrichment'),
    ]

    operations = [
        # Testing metadata fields
        migrations.AddField(
            model_name='playbookgraph',
            name='test_validation_status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('PASSED', 'Passed'),
                    ('FAILED', 'Failed'),
                    ('NOT_TESTED', 'Not Tested'),
                ],
                default='NOT_TESTED',
                help_text='Validation status from CI/CD test pipeline',
            ),
        ),
        migrations.AddField(
            model_name='playbookgraph',
            name='test_results',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text='Test execution results and validation outputs',
            ),
        ),
        migrations.AddField(
            model_name='playbookgraph',
            name='last_tested_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text='Timestamp of last test execution',
            ),
        ),
        # Tuning parameter fields
        migrations.AddField(
            model_name='playbookgraph',
            name='time_window',
            field=models.CharField(
                max_length=20,
                blank=True,
                help_text="Query time window (e.g., '5m', '1h', '24h')",
            ),
        ),
        migrations.AddField(
            model_name='playbookgraph',
            name='alert_threshold',
            field=models.IntegerField(
                null=True,
                blank=True,
                help_text='Alert threshold value',
            ),
        ),
        migrations.AddField(
            model_name='playbookgraph',
            name='threshold_operator',
            field=models.CharField(
                max_length=20,
                blank=True,
                choices=[
                    ('greater_than', 'Greater Than'),
                    ('less_than', 'Less Than'),
                    ('equals', 'Equals'),
                ],
                default='greater_than',
            ),
        ),
        migrations.AddField(
            model_name='playbookgraph',
            name='aggregation_field',
            field=models.CharField(
                max_length=100,
                blank=True,
                help_text="Field to aggregate by (e.g., 'user', 'host')",
            ),
        ),
        migrations.AddField(
            model_name='playbookgraph',
            name='aggregation_function',
            field=models.CharField(
                max_length=20,
                blank=True,
                choices=[
                    ('count', 'Count'),
                    ('sum', 'Sum'),
                    ('avg', 'Average'),
                    ('max', 'Maximum'),
                ],
                default='count',
            ),
        ),
        migrations.AddField(
            model_name='playbookgraph',
            name='suppression_window',
            field=models.CharField(
                max_length=20,
                blank=True,
                help_text="Alert suppression window (e.g., '1h')",
            ),
        ),
    ]
