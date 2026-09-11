"""
Test common MISP API endpoints to find the right one.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import requests
import json


class Command(BaseCommand):
    help = 'Test multiple MISP endpoints to identify the correct API paths'

    def handle(self, *args, **options):
        if not settings.MISP_ENABLED:
            self.stdout.write(self.style.ERROR("MISP is disabled!"))
            return

        base_url = settings.MISP_URL.rstrip('/')
        api_key = settings.MISP_API_KEY

        headers = {
            'Authorization': api_key,
            'Content-Type': 'application/json',
        }

        endpoints_to_test = [
            ('GET', '/servers/getVersion', None, 'Check MISP version'),
            ('GET', '/api/servers/getVersion', None, 'Version endpoint with /api prefix'),
            ('POST', '/events/add', {'Event': {'info': 'Test'}}, 'Create event (standard)'),
            ('POST', '/api/events/add', {'Event': {'info': 'Test'}}, 'Create event (with /api prefix)'),
            ('GET', '/api/events', None, 'List events (with /api)'),
        ]

        for method, endpoint, payload, description in endpoints_to_test:
            test_url = f'{base_url}{endpoint}'
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(self.style.HTTP_INFO(f"{method} {test_url}"))
            self.stdout.write(f"Description: {description}")

            try:
                if method == 'GET':
                    resp = requests.get(test_url, headers=headers, verify=settings.MISP_VERIFY_SSL, timeout=5)
                else:
                    resp = requests.post(test_url, json=payload, headers=headers, verify=settings.MISP_VERIFY_SSL, timeout=5)

                self.stdout.write(f"Status: HTTP {resp.status_code}")

                if resp.status_code in [200, 201]:
                    self.stdout.write(self.style.SUCCESS("✓ SUCCESS"))
                else:
                    self.stdout.write(self.style.WARNING(f"⚠ Unexpected status"))

                self.stdout.write(f"Response length: {len(resp.text)} bytes")
                if resp.text:
                    self.stdout.write(f"Response: {resp.text[:200]}")
                else:
                    self.stdout.write("Response: EMPTY")

            except requests.exceptions.Timeout:
                self.stdout.write(self.style.ERROR("✗ TIMEOUT"))
            except requests.exceptions.ConnectionError as e:
                self.stdout.write(self.style.ERROR(f"✗ CONNECTION ERROR: {str(e)[:100]}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"✗ ERROR: {str(e)}"))
