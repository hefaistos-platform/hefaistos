# Merge migration to resolve conflicting branches

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0002_alter_userraisettings_preferred_model'),
        ('ai_assistant', '0003_alter_useraisettings_claude_api_key_and_more'),
    ]

    operations = [
    ]
