#!/usr/bin/env python
"""
Test script to verify GraphQL authentication works with JWT tokens.
Run from deploy_connector container.
Usage: python test_graphql.py
"""
import requests
import json
import sys
import time

# Configuration
BASE_URL = "http://backend:8000"
GRAPHQL_URL = f"{BASE_URL}/graphql"
TOKEN_URL = f"{BASE_URL}/api/token/"

# Credentials for the connector user
USERNAME = "connector"
PASSWORD = "changeme"

print("\n" + "=" * 70)
print("GraphQL Authentication Test")
print("=" * 70)

# Retry logic for API availability
max_retries = 10
retry_count = 0
while retry_count < max_retries:
    try:
        # Step 1: Obtain JWT token
        print(f"\n[1/3] Obtaining JWT token from {TOKEN_URL}...")
        token_response = requests.post(
            TOKEN_URL,
            json={"username": USERNAME, "password": PASSWORD},
            timeout=5
        )
        print(f"      Status: {token_response.status_code}")
        
        if token_response.status_code == 200:
            token_data = token_response.json()
            access_token = token_data.get('access')
            if access_token:
                print(f"      ✓ Token obtained: {access_token[:50]}...")
                break
        else:
            print(f"      ✗ Error: {token_response.text}")
            
    except requests.exceptions.ConnectionError as e:
        retry_count += 1
        if retry_count < max_retries:
            print(f"      ✗ Connection failed (Attempt {retry_count}/{max_retries})")
            print(f"      Retrying in 5 seconds...")
            time.sleep(5)
        else:
            print(f"      ✗ Failed after {max_retries} attempts")
            sys.exit(1)
    except Exception as e:
        print(f"      ✗ Unexpected error: {e}")
        sys.exit(1)

# Step 2: Query GraphQL without authentication
print(f"\n[2/3] Testing GraphQL without authentication...")
try:
    graphql_response = requests.post(
        GRAPHQL_URL,
        json={"query": "{ me { username } }"},
        timeout=5
    )
    print(f"      Status: {graphql_response.status_code}")
    data = graphql_response.json()
    if 'errors' in data:
        print(f"      Expected error (unauthenticated): {data['errors'][0]['message']}")
    else:
        print(f"      Unexpected response: {data}")
except Exception as e:
    print(f"      ✗ Request failed: {e}")

# Step 3: Query GraphQL WITH JWT authentication
print(f"\n[3/3] Testing GraphQL WITH authentication...")
try:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    graphql_response = requests.post(
        GRAPHQL_URL,
        json={"query": "{ me { username organization { name } } }"},
        headers=headers,
        timeout=5
    )
    print(f"      Status: {graphql_response.status_code}")
    
    data = graphql_response.json()
    
    if 'errors' in data:
        print(f"      ✗ GraphQL errors:")
        for error in data['errors']:
            print(f"         {error.get('message')}")
        print(f"\n      Full response: {json.dumps(data, indent=2)}")
    elif data.get('data', {}).get('me'):
        me = data['data']['me']
        print(f"      ✓ Authentication successful!")
        print(f"         Username: {me.get('username')}")
        print(f"         Organization: {me.get('organization', {}).get('name', 'N/A')}")
        print(f"\n" + "=" * 70)
        print("✓ ALL TESTS PASSED - GraphQL authentication is working!")
        print("=" * 70)
    else:
        print(f"      ✗ No user data returned")
        print(f"      Response: {json.dumps(data, indent=2)}")
        
except Exception as e:
    print(f"      ✗ Request failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

