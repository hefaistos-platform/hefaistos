#!/usr/bin/env python
"""
Test script to verify GraphQL authentication with the static JWT token.
Run from deploy_connector container.
Usage: python test_graphql.py

This tests that HEFAISTOS_API_TOKEN is correctly set and can authenticate to GraphQL.
"""
import requests
import json
import sys
import os

# Configuration from environment
HEFAISTOS_API_URL = os.environ.get('HEFAISTOS_API_URL')
HEFAISTOS_API_TOKEN = os.environ.get('HEFAISTOS_API_TOKEN')

if not HEFAISTOS_API_URL or not HEFAISTOS_API_TOKEN:
    print("ERROR: Missing required environment variables:")
    print(f"  - HEFAISTOS_API_URL: {HEFAISTOS_API_URL}")
    print(f"  - HEFAISTOS_API_TOKEN: {HEFAISTOS_API_TOKEN}")
    sys.exit(1)

print("\n" + "=" * 70)
print("GraphQL Authentication Test")
print("=" * 70)
print(f"\nAPI URL: {HEFAISTOS_API_URL}")
print(f"Token: {HEFAISTOS_API_TOKEN[:50]}...")

# Test GraphQL with JWT token
print(f"\nSending GraphQL query with Bearer token...")
try:
    headers = {
        "Authorization": f"Bearer {HEFAISTOS_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    graphql_response = requests.post(
        HEFAISTOS_API_URL,
        json={"query": "{ me { username organization { name } } }"},
        headers=headers,
        timeout=10
    )
    
    print(f"Status Code: {graphql_response.status_code}")
    data = graphql_response.json()
    
    print(f"\nResponse:")
    print(json.dumps(data, indent=2))
    
    if 'errors' in data and data['errors']:
        print(f"\n✗ GraphQL errors detected:")
        for error in data['errors']:
            print(f"   - {error.get('message')}")
        sys.exit(1)
    elif data.get('data', {}).get('me'):
        me = data['data']['me']
        print(f"\n✓ SUCCESS! Authentication successful!")
        print(f"   Username: {me.get('username')}")
        print(f"   Organization: {me.get('organization', {}).get('name', 'N/A')}")
        print("\n" + "=" * 70)
        sys.exit(0)
    else:
        print(f"\n✗ Unexpected response - no user data")
        sys.exit(1)
        
except Exception as e:
    print(f"\n✗ Request failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
