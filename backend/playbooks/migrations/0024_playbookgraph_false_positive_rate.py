from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0023_reviewrequest_reviewcomment'),
    ]

    # Legacy migration left intentionally as a no-op to avoid conflicts
    operations = []
