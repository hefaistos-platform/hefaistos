from django.db import migrations, models

class Migration(migrations.Migration):

    # NOTE: This migration was superseded by 0026_add_test_fields.
    # To avoid branching the graph, make this a no-op that depends on the
    # latest known head in this repository.
    # Make this historical stub depend on the real field-adding migration to avoid branching.
    dependencies = [
        ('playbooks', '0026_add_test_fields'),
    ]

    operations = []
