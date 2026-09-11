"""
Raw HTTP test for MISP API - useful for debugging connectivity issues.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import requests
import json


class Command(BaseCommand):
    help = 'Raw HTTP test for MISP API connectivity'

    def add_arguments(self, parser):
        parser.add_argument('--endpoint', type=str, default='/events/add', help='API endpoint to test')
        parser.add_argument('--method', type=str, default='GET', choices=['GET', 'POST'], help='HTTP method')

    def handle(self, *args, **options):
        if not settings.MISP_ENABLED:
            self.stdout.write(self.style.ERROR("MISP is disabled!"))
            return

        url = settings.MISP_URL.rstrip('/')
        api_key = settings.MISP_API_KEY
        endpoint = options.get('endpoint', '/events/add')
        method = options.get('method', 'GET')

        self.stdout.write(self.style.HTTP_INFO(f"Testing MISP API: {method} {url}{endpoint}"))
        self.stdout.write(f"API Key: {api_key[:20]}...")

        headers = {
            'Authorization': api_key,
            'Content-Type': 'application/json',
        }

        try:
            if method == 'GET':
                # Test GET /servers/getVersion
                test_url = f'{url}/servers/getVersion'
                self.stdout.write(f"\nTest 1: GET {test_url}")
                resp = requests.get(test_url, headers=headers, verify=settings.MISP_VERIFY_SSL, timeout=10)
                self._print_response(resp)

            elif method == 'POST':
                # Test POST /events/add
                test_url = f'{url}/events/add'
                self.stdout.write(f"\nTest 2: POST {test_url}")
                payload = {
                    'Event': {
                        'info': 'Test Event',
                        'distribution': 3,
                        'threat_level_id': 3,
                        'analysis': 0,
                        'published': False,
                    }
                }
                self.stdout.write(f"Payload: {json.dumps(payload, indent=2)}")
                resp = requests.post(
                    test_url,
                    json=payload,
                    headers=headers,
                    verify=settings.MISP_VERIFY_SSL,
                    timeout=10
                )
                self._print_response(resp)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
            import traceback
            traceback.print_exc()

    def _print_response(self, resp):
        self.stdout.write(f"Status: {resp.status_code}")
        self.stdout.write(f"Headers: {dict(resp.headers)}")
        self.stdout.write(f"Body length: {len(resp.text)}")
        self.stdout.write(f"Body: {resp.text[:500]}")

        # Try to parse as JSON
        try:
            json_data = resp.json()
            self.stdout.write(self.style.SUCCESS(f"Valid JSON: {json.dumps(json_data, indent=2)[:500]}"))
        except:
            self.stdout.write(f"Not JSON: {resp.text[:200]}")
