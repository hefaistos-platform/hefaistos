#!/usr/bin/env python
"""
Simplified GraphQL authentication test - debug version.
Tests different query formats to isolate the issue.
"""
import requests
import json
import sys
import os

HEFAISTOS_API_URL = os.environ.get('HEFAISTOS_API_URL')
HEFAISTOS_API_TOKEN = os.environ.get('HEFAISTOS_API_TOKEN')

if not HEFAISTOS_API_URL or not HEFAISTOS_API_TOKEN:
    print(f"Missing env vars: URL={HEFAISTOS_API_URL}, TOKEN={bool(HEFAISTOS_API_TOKEN)}")
    sys.exit(1)

print("\n" + "=" * 70)
print("GraphQL Debug Test - Testing Different Query Formats")
print("=" * 70)

headers = {
    "Authorization": f"Bearer {HEFAISTOS_API_TOKEN}",
    "Content-Type": "application/json"
}

# Test 1: Simple query - just me.username
print("\n[Test 1] Simple query: { me { username } }")
try:
    response = requests.post(
        HEFAISTOS_API_URL,
        json={"query": "{ me { username } }"},
        headers=headers,
        timeout=10
    )
    data = response.json()
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(data, indent=2)}")
    if data.get('data', {}).get('me'):
        print("✓ SUCCESS")
    elif data.get('errors'):
        print(f"✗ Error: {data['errors'][0]['message']}")
except Exception as e:
    print(f"✗ Exception: {e}")

# Test 2: Query with id
print("\n[Test 2] Query with id: { me { id username } }")
try:
    response = requests.post(
        HEFAISTOS_API_URL,
        json={"query": "{ me { id username } }"},
        headers=headers,
        timeout=10
    )
    data = response.json()
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(data, indent=2)}")
    if data.get('data', {}).get('me'):
        print("✓ SUCCESS")
    elif data.get('errors'):
        print(f"✗ Error: {data['errors'][0]['message']}")
except Exception as e:
    print(f"✗ Exception: {e}")

# Test 3: Query with organization (no nested fields)
print("\n[Test 3] Query with organization: { me { username organization } }")
try:
    response = requests.post(
        HEFAISTOS_API_URL,
        json={"query": "{ me { username organization } }"},
        headers=headers,
        timeout=10
    )
    data = response.json()
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(data, indent=2)}")
    if data.get('data', {}).get('me'):
        print("✓ SUCCESS")
    elif data.get('errors'):
        print(f"✗ Error: {data['errors'][0]['message']}")
except Exception as e:
    print(f"✗ Exception: {e}")

# Test 4: Full query with nested organization
print("\n[Test 4] Full query: { me { username organization { name } } }")
try:
    response = requests.post(
        HEFAISTOS_API_URL,
        json={"query": "{ me { username organization { name } } }"},
        headers=headers,
        timeout=10
    )
    data = response.json()
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(data, indent=2)}")
    if data.get('data', {}).get('me'):
        print("✓ SUCCESS")
    elif data.get('errors'):
        print(f"✗ Error: {data['errors'][0]['message']}")
except Exception as e:
    print(f"✗ Exception: {e}")

# Test 5: Query without authentication to see expected error
print("\n[Test 5] Query WITHOUT token (expect auth error): { me { username } }")
try:
    response = requests.post(
        HEFAISTOS_API_URL,
        json={"query": "{ me { username } }"},
        timeout=10
    )
    data = response.json()
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(data, indent=2)}")
    if data.get('errors'):
        print(f"Expected error: {data['errors'][0]['message']}")
except Exception as e:
    print(f"✗ Exception: {e}")

print("\n" + "=" * 70)
