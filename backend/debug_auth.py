#!/usr/bin/env python
"""
Django shell script to diagnose connector user and GraphQL auth issues.
Run as: python manage.py shell < debug_auth.py
"""

from django.contrib.auth import get_user_model
from organizations.models import Organization
from graphene_django.views import GraphQLView
import json

User = get_user_model()

print("\n" + "="*60)
print("HEFAISTOS Auth Debugging")
print("="*60)

# Check if connector user exists
print("\n[1] Checking for 'connector' user...")
try:
    connector = User.objects.get(username='connector')
    print(f"✓ User found:")
    print(f"  - ID: {connector.id}")
    print(f"  - Username: {connector.username}")
    print(f"  - Email: {connector.email}")
    print(f"  - Organization: {connector.organization}")
    print(f"  - Is Active: {connector.is_active}")
    print(f"  - Is Staff: {connector.is_staff}")
except User.DoesNotExist:
    print("✗ 'connector' user does NOT exist - THIS IS THE PROBLEM")
    print("  Creating it now...")
    org, created = Organization.objects.get_or_create(name='System')
    connector = User.objects.create_user(
        username='connector',
        password='changeme',
        email='connector@system.local',
        organization=org
    )
    print(f"✓ Created connector user with organization: {org.name}")

# List all users
print("\n[2] All users in database:")
for u in User.objects.all():
    print(f"  - {u.id}: {u.username} (org: {u.organization})")

# List all organizations
print("\n[3] All organizations:")
for org in Organization.objects.all():
    print(f"  - {org.id}: {org.name} ({org.members.count()} members)")

print("\n" + "="*60)
