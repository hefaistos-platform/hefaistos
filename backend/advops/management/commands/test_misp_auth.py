"""
Verify MISP API key and test authentication methods to find the correct format.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import requests
import json


class Command(BaseCommand):
    help = 'Test different MISP authentication methods'

    def handle(self, *args, **options):
        if not settings.MISP_ENABLED:
            self.stdout.write(self.style.ERROR("MISP is disabled!"))
            return

        base_url = settings.MISP_URL.rstrip('/')
        api_key = settings.MISP_API_KEY

        self.stdout.write(self.style.HTTP_INFO(f"\n{'='*70}"))
        self.stdout.write(self.style.HTTP_INFO("MISP API Authentication Tester"))
        self.stdout.write(self.style.HTTP_INFO(f"{'='*70}"))
        
        self.stdout.write(f"\nMISP URL: {base_url}")
        self.stdout.write(f"API Key (first 20 chars): {api_key[:20]}...")
        self.stdout.write(f"API Key length: {len(api_key)} characters")
        self.stdout.write(f"Verify SSL: {settings.MISP_VERIFY_SSL}\n")

        # Define authentication methods to test
        auth_methods = [
            {
                'name': 'Authorization header (standard)',
                'headers': {'Authorization': api_key},
                'endpoint': '/servers/getVersion',
            },
            {
                'name': 'X-MISP-Auth header',
                'headers': {'X-MISP-Auth': api_key},
                'endpoint': '/servers/getVersion',
            },
            {
                'name': 'X-API-Key header',
                'headers': {'X-API-Key': api_key},
                'endpoint': '/servers/getVersion',
            },
            {
                'name': 'With /api prefix + Authorization',
                'headers': {'Authorization': api_key},
                'endpoint': '/api/servers/getVersion',
            },
            {
                'name': 'With /api prefix + X-API-Key',
                'headers': {'X-API-Key': api_key},
                'endpoint': '/api/servers/getVersion',
            },
        ]

        success_count = 0

        for method in auth_methods:
            self.stdout.write(f"\n{'-'*70}")
            self.stdout.write(self.style.HTTP_INFO(f"Method: {method['name']}"))
            
            endpoint = method['endpoint']
            test_url = f'{base_url}{endpoint}'
            
            self.stdout.write(f"URL: {test_url}")
            self.stdout.write(f"Headers: {method['headers']}")

            try:
                headers = {
                    'Content-Type': 'application/json',
                    **method['headers']
                }

                resp = requests.get(
                    test_url,
                    headers=headers,
                    verify=settings.MISP_VERIFY_SSL,
                    timeout=10
                )

                self.stdout.write(f"Status: HTTP {resp.status_code}")

                # Check response type
                if resp.text.startswith('{') or resp.text.startswith('['):
                    self.stdout.write(self.style.SUCCESS("✓ SUCCESS - Got JSON response!"))
                    success_count += 1
                    try:
                        data = resp.json()
                        # Pretty print first 300 chars
                        response_str = json.dumps(data, indent=2)
                        self.stdout.write(f"Response preview:\n{response_str[:300]}\n")
                    except:
                        self.stdout.write(f"Response: {resp.text[:200]}\n")
                        
                elif '<html>' in resp.text.lower() or 'login' in resp.text.lower():
                    self.stdout.write(self.style.ERROR("✗ FAILED - Got HTML login page"))
                    self.stdout.write("This means authentication failed for this method")
                else:
                    self.stdout.write(f"Response type: {resp.headers.get('Content-Type', 'unknown')}")
                    self.stdout.write(f"Response preview: {resp.text[:100]}")

            except requests.exceptions.Timeout:
                self.stdout.write(self.style.ERROR("✗ TIMEOUT - Server not responding"))
            except requests.exceptions.ConnectionError as e:
                self.stdout.write(self.style.ERROR(f"✗ CONNECTION ERROR: {str(e)[:80]}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"✗ ERROR: {str(e)}"))

        # Summary
        self.stdout.write(f"\n{'='*70}")
        if success_count > 0:
            self.stdout.write(self.style.SUCCESS(f"\n✓ Found {success_count} working authentication method(s)!"))
            self.stdout.write("Use the first successful method above in the code.\n")
        else:
            self.stdout.write(self.style.ERROR("\n✗ No authentication methods worked!"))
            self.stdout.write("\nPossible issues:")
            self.stdout.write("1. API key is incorrect - check MISP admin panel")
            self.stdout.write("2. MISP user doesn't have API permissions - enable in admin panel")
            self.stdout.write("3. MISP user is disabled - enable the user account")
            self.stdout.write("4. Firewall blocking the connection\n")
            
            self.stdout.write("Next steps:")
            self.stdout.write("1. Log in to MISP web interface as admin")
            self.stdout.write("2. Go to Administration → Users")
            self.stdout.write("3. Find your user and check:")
            self.stdout.write("   - User is ENABLED (not disabled)")
            self.stdout.write("   - Copy the 'Authkey' field (not password)")
            self.stdout.write("4. Update the MISP_API_KEY with the correct authkey")
            self.stdout.write("5. Run this command again\n")

        self.stdout.write(f"{'='*70}\n")
