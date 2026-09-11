from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0003_detectionplaybook_detection_rules_and_more'),
    ]

    # Legacy migration left intentionally as a no-op to avoid conflicts
    operations = []
