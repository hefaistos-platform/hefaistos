import os
import django
import json
from graphene.test import Client

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.core.settings")
django.setup()

from backend.core.schema import schema
from backend.identity.models import CustomUser, Organization

def test_mutation():
    # Ensure we have a user and org
    org, _ = Organization.objects.get_or_create(name="Test Org")
    user, _ = CustomUser.objects.get_or_create(username="testadmin", defaults={'organization': org, 'role': 'ADMIN'})
    
    client = Client(schema)
    
    mutation = """
    mutation {
      createPlaybookGraph(title: "New Malware Analysis") {
        graph { id nodes { id layerName } }
      }
    }
    """
    
    # Mock context with user
    class Context:
        def __init__(self, user):
            self.user = user
            
    context = Context(user)
    
    result = client.execute(mutation, context=context)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    test_mutation()
