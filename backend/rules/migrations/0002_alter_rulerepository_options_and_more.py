# Recreated migration to replace removed original 0002 and align with current models
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('rules', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rulerepository',
            name='git_url',
            field=models.URLField(max_length=500, blank=True, null=True, help_text='Clone URL (e.g., https://github.com/SigmaHQ/sigma.git)'),
        ),
        migrations.AddField(
            model_name='rulerepository',
            name='username',
            field=models.CharField(max_length=512, blank=True, null=True, help_text='Encrypted username or app ID'),
        ),
        migrations.AddField(
            model_name='rulerepository',
            name='_token',
            field=models.TextField(blank=True, null=True, db_column='token', help_text='Encrypted access token (do not access directly)'),
        ),
    ]
