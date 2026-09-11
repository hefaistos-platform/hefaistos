from django.db import migrations


class _PgOnlySQL(migrations.RunSQL):
    """A RunSQL subclass that skips execution on non-PostgreSQL databases."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == 'postgresql':
            super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == 'postgresql':
            super().database_backwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):
    dependencies = [
        ('rules', '0006_merge_0002_0005'),
    ]

    operations = [
        _PgOnlySQL("CREATE EXTENSION IF NOT EXISTS pg_trgm;"),
        _PgOnlySQL(
            "CREATE INDEX IF NOT EXISTS idx_rules_title_trgm ON rules_detectionrule USING gin (title gin_trgm_ops);"
        ),
        _PgOnlySQL(
            "CREATE INDEX IF NOT EXISTS idx_rules_desc_trgm ON rules_detectionrule USING gin (description gin_trgm_ops);"
        ),
        _PgOnlySQL(
            "CREATE INDEX IF NOT EXISTS idx_rules_raw_trgm ON rules_detectionrule USING gin (raw_content gin_trgm_ops);"
        ),
    ]
