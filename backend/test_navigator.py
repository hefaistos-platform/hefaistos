import os
import django
import json
from graphene.test import Client

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.core.settings")
django.setup()

from backend.core.schema import schema
from backend.identity.models import CustomUser, Organization
from backend.playbooks.models import PlaybookGraph, PlaybookNode, DetectionPlaybook
from backend.platform_data.models import MitreAttackTechnique

def test_navigator_query():
    # 1. Setup Data
    org, _ = Organization.objects.get_or_create(name="Test Org")
    user, _ = CustomUser.objects.get_or_create(username="testadmin", defaults={'organization': org, 'role': 'ADMIN'})
    
    # Create Technique
    tech, _ = MitreAttackTechnique.objects.get_or_create(
        technique_id="T1003", 
        defaults={'name': 'Credential Dumping'}
    )
    
    # Create Graph
    graph = PlaybookGraph.objects.create(
        title="Test Graph",
        organization=org,
        author=user,
        status=DetectionPlaybook.PlaybookStatus.DEPLOYED
    )
    
    # Create Node
    node = PlaybookNode.objects.create(
        graph=graph,
        layer_name="Test Node",
        position_x=0,
        position_y=0
    )
    
    # Link Node to Technique
    node.mitre_attack_mappings.add(tech)
    
    print(f"Graph Status: {graph.status}")
    print(f"Node Mappings: {node.mitre_attack_mappings.all()}")
    
    # 2. Run Query
    client = Client(schema)
    
    query = """
    query {
      attackNavigatorLayer
    }
    """
    
    class Context:
        def __init__(self, user):
            self.user = user
            
    context = Context(user)
    
    result = client.execute(query, context=context)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    test_navigator_query()
