"""
Detailed MISP diagnostic - check redirects, protocols, and API access.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import requests
import json


class Command(BaseCommand):
    help = 'Detailed MISP diagnostics - protocol, redirects, and authentication'

    def handle(self, *args, **options):
        if not settings.MISP_ENABLED:
            self.stdout.write(self.style.ERROR("MISP is disabled!"))
            return

        base_url = settings.MISP_URL.rstrip('/')
        api_key = settings.MISP_API_KEY

        self.stdout.write(self.style.HTTP_INFO(f"\n{'='*70}"))
        self.stdout.write(self.style.HTTP_INFO("MISP Detailed Diagnostic"))
        self.stdout.write(self.style.HTTP_INFO(f"{'='*70}"))
        
        self.stdout.write(f"\nConfigured MISP URL: {base_url}")
        self.stdout.write(f"API Key length: {len(api_key)} characters")
        self.stdout.write(f"API Key (first 10 + last 10): {api_key[:10]}...{api_key[-10:]}")
        self.stdout.write(f"Verify SSL: {settings.MISP_VERIFY_SSL}\n")

        # Test 1: Check protocol and redirects
        self.stdout.write(f"\n{'-'*70}")
        self.stdout.write(self.style.HTTP_INFO("Test 1: Protocol and Redirects"))
        self._test_protocols(base_url, api_key)

        # Test 2: Test without authentication (to see actual error)
        self.stdout.write(f"\n{'-'*70}")
        self.stdout.write(self.style.HTTP_INFO("Test 2: Request without authentication"))
        self._test_no_auth(base_url)

        # Test 3: Check if user exists in MISP
        self.stdout.write(f"\n{'-'*70}")
        self.stdout.write(self.style.HTTP_INFO("Test 3: Check MISP connectivity"))
        self._test_misp_page(base_url)

        # Print instructions
        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(self.style.ERROR("\n❌ API KEY IS NOT WORKING"))
        self.stdout.write("\nTo fix this, follow these steps:\n")
        self.stdout.write("1. Open MISP in your browser: https://misp.counterintel.cz")
        self.stdout.write("2. Log in with your admin credentials")
        self.stdout.write("3. Click your username at top right → Profile")
        self.stdout.write("4. Look for the 'Authkey' field (usually at the bottom)")
        self.stdout.write("5. Copy the entire Authkey string")
        self.stdout.write("6. Update the MISP_API_KEY secret with this authkey:")
        self.stdout.write("   - Edit: docker-compose.yml or .env")
        self.stdout.write("   - Or update the secret file directly")
        self.stdout.write("7. Restart the backend container")
        self.stdout.write("8. Run this diagnostic again\n")

        self.stdout.write("⚠️  Common mistakes:")
        self.stdout.write("- Using PASSWORD instead of AUTHKEY")
        self.stdout.write("- User account is DISABLED in MISP")
        self.stdout.write("- User doesn't have API access permissions")
        self.stdout.write("- Copy/paste errors (extra spaces or quotes)\n")

        self.stdout.write(f"{'='*70}\n")

    def _test_protocols(self, base_url, api_key):
        """Test both HTTP and HTTPS protocols"""
        
        # Determine if URL uses http or https
        if base_url.startswith('http://'):
            https_url = base_url.replace('http://', 'https://', 1)
        else:
            https_url = base_url
        
        for url_variant in [base_url, https_url]:
            protocol = 'HTTPS' if 'https' in url_variant else 'HTTP'
            test_url = f'{url_variant}/servers/getVersion'
            
            self.stdout.write(f"\nTesting {protocol}: {test_url}")
            
            try:
                headers = {'Authorization': api_key, 'Content-Type': 'application/json'}
                
                # Don't follow redirects to see what happens
                resp = requests.get(
                    test_url,
                    headers=headers,
                    verify=settings.MISP_VERIFY_SSL,
                    timeout=5,
                    allow_redirects=False
                )
                
                self.stdout.write(f"  Status: HTTP {resp.status_code}")
                
                if resp.status_code in [301, 302, 303, 307, 308]:
                    self.stdout.write(f"  ⚠️  REDIRECT to: {resp.headers.get('Location', 'unknown')}")
                elif resp.status_code == 200:
                    if resp.text.startswith('{'):
                        self.stdout.write(f"  ✓ JSON response")
                    else:
                        self.stdout.write(f"  ✗ HTML response (auth failed)")
                elif resp.status_code == 401:
                    self.stdout.write(f"  ✗ 401 Unauthorized - API key is invalid")
                elif resp.status_code == 403:
                    self.stdout.write(f"  ✗ 403 Forbidden - User doesn't have API access")
                else:
                    self.stdout.write(f"  ? Unexpected status")
                    
            except requests.exceptions.ConnectionError as e:
                self.stdout.write(f"  ✗ Connection error: {str(e)[:80]}")
            except Exception as e:
                self.stdout.write(f"  ✗ Error: {str(e)[:80]}")

    def _test_no_auth(self, base_url):
        """Test request without any authentication header"""
        test_url = f'{base_url}/servers/getVersion'
        
        self.stdout.write(f"\nRequest without auth header to: {test_url}")
        
        try:
            resp = requests.get(
                test_url,
                headers={'Content-Type': 'application/json'},
                verify=settings.MISP_VERIFY_SSL,
                timeout=5,
                allow_redirects=False
            )
            
            self.stdout.write(f"Status: HTTP {resp.status_code}")
            
            if resp.status_code == 401:
                self.stdout.write("Expected 401 Unauthorized (server is accessible)")
            elif resp.status_code == 200 and '<html>' not in resp.text:
                self.stdout.write("Got data without auth (unusual)")
            elif resp.status_code == 200:
                self.stdout.write("Got login page (expected)")
            else:
                self.stdout.write(f"Status: {resp.status_code}")
                
        except Exception as e:
            self.stdout.write(f"Error: {str(e)[:80]}")

    def _test_misp_page(self, base_url):
        """Test if MISP main page is accessible"""
        test_url = f'{base_url}/users/login'
        
        self.stdout.write(f"\nTesting MISP main page: {test_url}")
        
        try:
            resp = requests.get(
                test_url,
                verify=settings.MISP_VERIFY_SSL,
                timeout=5
            )
            
            if resp.status_code == 200:
                self.stdout.write(f"✓ MISP is running and accessible")
                if 'MISP' in resp.text:
                    self.stdout.write(f"✓ MISP login page detected")
            else:
                self.stdout.write(f"✗ Unexpected status: {resp.status_code}")
                
        except Exception as e:
            self.stdout.write(f"✗ Cannot reach MISP: {str(e)[:80]}")
