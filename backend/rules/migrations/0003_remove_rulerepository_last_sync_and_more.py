# Replacement for missing original 0003 migration.
# The original attempted to remove a non-existent 'last_sync' field,
# causing KeyError during migrate. This stub maintains graph continuity
# without destructive operations.
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('rules', '0002_alter_rulerepository_options_and_more'),
    ]

    operations = [
        # Intentionally left empty; previous refactor aligned model fields.
    ]
