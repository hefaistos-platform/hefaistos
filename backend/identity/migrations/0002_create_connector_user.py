# Generated migration to create the connector service user

from django.db import migrations
from django.contrib.auth import get_user_model
from django.conf import settings

def create_connector_user(apps, schema_editor):
    """Create the connector_svc service user if it doesn't exist."""
    User = apps.get_model(settings.AUTH_USER_MODEL)
    Organization = apps.get_model('organizations', 'Organization')
    
    # Get or create a default organization for the connector
    org, created = Organization.objects.get_or_create(
        name='System',
        defaults={'name': 'System'}
    )
    
    # Create the connector_svc user if it doesn't already exist
    if not User.objects.filter(username='connector_svc').exists():
        User.objects.create_user(
            username='connector_svc',
            password='changeme',
            email='connector@system.local',
            organization=org
        )

def reverse_func(apps, schema_editor):
    """Delete the connector_svc user if needed (optional)."""
    User = apps.get_model(settings.AUTH_USER_MODEL)
    User.objects.filter(username='connector_svc').delete()

class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0001_initial'),
        ('organizations', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_connector_user, reverse_func),
    ]
