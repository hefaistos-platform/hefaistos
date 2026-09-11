"""
Helper command to verify/test MISP API key manually.
Shows you exactly where to get the authkey and how to test it.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import requests


class Command(BaseCommand):
    help = 'Manual MISP API key verification'

    def add_arguments(self, parser):
        parser.add_argument('--key', type=str, help='Test a specific API key')

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO(f"\n{'='*70}"))
        self.stdout.write(self.style.HTTP_INFO("MISP API Key Verification Tool"))
        self.stdout.write(self.style.HTTP_INFO(f"{'='*70}\n"))

        # If key provided, test it
        if options.get('key'):
            test_key = options.get('key')
            self.stdout.write(f"Testing API key: {test_key[:20]}...\n")
            self._test_api_key(test_key)
            return

        # Otherwise, show instructions
        self.stdout.write(self.style.WARNING("⚠️  INSTRUCTIONS TO GET YOUR API KEY FROM MISP:\n"))

        self.stdout.write(self.style.SUCCESS("Step 1: Open MISP"))
        self.stdout.write("   Open in browser: https://misp.counterintel.cz\n")

        self.stdout.write(self.style.SUCCESS("Step 2: Log In"))
        self.stdout.write("   Log in with your MISP username and password\n")

        self.stdout.write(self.style.SUCCESS("Step 3: Go to Your Profile"))
        self.stdout.write("   Click your username in the top-right corner")
        self.stdout.write("   Select 'Profile' from the dropdown menu\n")

        self.stdout.write(self.style.SUCCESS("Step 4: Find Your Authkey"))
        self.stdout.write("   Look for a field labeled 'Authkey' (usually at the bottom)")
        self.stdout.write("   It will look like: lzKbe82cl5Xyth9173XDBCWV7dCYwihbys3CEBoV")
        self.stdout.write("   ⚠️  Make sure you copy the AUTHKEY, not the password!\n")

        self.stdout.write(self.style.SUCCESS("Step 5: Test Your Key"))
        self.stdout.write("   Once you have the authkey, run this command:")
        self.stdout.write("   docker compose exec backend python manage.py test_misp_key --key YOUR_AUTHKEY_HERE\n")

        self.stdout.write(self.style.SUCCESS("Step 6: Update the Secret"))
        if settings.MISP_ENABLED:
            self.stdout.write("   If the test passes, update your configuration:")
            self.stdout.write("   1. Find where the secret is stored (docker-compose.yml or .env)")
            self.stdout.write("   2. Update MISP_API_KEY with your correct authkey")
            self.stdout.write("   3. Restart backend: docker compose restart backend\n")

        # Show current config
        self.stdout.write(self.style.WARNING("\n📋 Current Configuration:"))
        self.stdout.write(f"MISP_ENABLED: {settings.MISP_ENABLED}")
        self.stdout.write(f"MISP_URL: {settings.MISP_URL}")
        self.stdout.write(f"Current API Key length: {len(settings.MISP_API_KEY)} chars")
        self.stdout.write(f"Current API Key (first/last): {settings.MISP_API_KEY[:10]}...{settings.MISP_API_KEY[-10:]}\n")

        self.stdout.write(f"{'='*70}\n")

    def _test_api_key(self, api_key):
        """Test a given API key against MISP"""
        base_url = settings.MISP_URL.rstrip('/')
        
        # Normalize to HTTPS
        if base_url.startswith('http://'):
            base_url = base_url.replace('http://', 'https://', 1)
        
        test_url = f'{base_url}/servers/getVersion'
        
        self.stdout.write(f"Testing URL: {test_url}")
        self.stdout.write(f"API Key: {api_key[:20]}...\n")

        try:
            headers = {
                'Authorization': api_key,
                'Content-Type': 'application/json',
            }

            resp = requests.get(
                test_url,
                headers=headers,
                verify=settings.MISP_VERIFY_SSL,
                timeout=10,
                allow_redirects=True  # Follow redirects
            )

            self.stdout.write(f"Final Status: HTTP {resp.status_code}\n")

            # Check response
            if resp.text.startswith('{'):
                self.stdout.write(self.style.SUCCESS("✓ SUCCESS - Got JSON response!"))
                try:
                    import json
                    data = resp.json()
                    self.stdout.write(f"\nMISP Version: {data.get('version', 'unknown')}")
                    self.stdout.write(f"Response: {json.dumps(data, indent=2)[:300]}\n")
                    
                    self.stdout.write(self.style.SUCCESS("\n✅ API KEY IS VALID!"))
                    self.stdout.write("Update your configuration with this key and restart the backend.\n")
                except:
                    self.stdout.write(f"Response: {resp.text[:200]}\n")

            elif '<html>' in resp.text.lower() or 'login' in resp.text.lower():
                self.stdout.write(self.style.ERROR("✗ FAILED - Got login page (auth failed)"))
                self.stdout.write("This API key is not valid or user doesn't have API access.\n")
                self.stdout.write("Check:")
                self.stdout.write("1. Is the Authkey correct? (copy/paste from MISP profile)")
                self.stdout.write("2. Is the user ENABLED in MISP?")
                self.stdout.write("3. Does the user have API access permissions?\n")
            else:
                self.stdout.write(f"Unexpected response type")
                self.stdout.write(f"Response: {resp.text[:200]}\n")

        except requests.exceptions.Timeout:
            self.stdout.write(self.style.ERROR("✗ TIMEOUT - Server not responding"))
        except requests.exceptions.ConnectionError as e:
            self.stdout.write(self.style.ERROR(f"✗ CONNECTION ERROR: {str(e)[:80]}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ ERROR: {str(e)}"))
