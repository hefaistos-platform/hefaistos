from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rules', '0018_autocompleteevent_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='rulerepository',
            name='provider',
            field=models.CharField(
                choices=[
                    ('AUTO', 'Auto-detect'),
                    ('GITHUB', 'GitHub'),
                    ('GITLAB', 'GitLab'),
                    ('GITEA', 'Gitea'),
                ],
                default='AUTO',
                help_text='Git repository provider. AUTO derives provider from git_url host.',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='rulerepository',
            name='api_base_url',
            field=models.URLField(
                blank=True,
                help_text='Optional custom API base URL for self-hosted providers (e.g., https://gitlab.example.com/api/v4).',
                max_length=500,
                null=True,
            ),
        ),
    ]
