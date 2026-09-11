"""
Direct HTTP test - send raw request and examine full response.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import requests
import json


class Command(BaseCommand):
    help = 'Send direct HTTP request and examine full response'

    def handle(self, *args, **options):
        base_url = settings.MISP_URL.rstrip('/')
        if base_url.startswith('http://'):
            base_url = base_url.replace('http://', 'https://', 1)
        
        api_key = settings.MISP_API_KEY
        
        self.stdout.write(self.style.HTTP_INFO(f"\n{'='*80}"))
        self.stdout.write(self.style.HTTP_INFO("MISP Direct HTTP Request Test"))
        self.stdout.write(self.style.HTTP_INFO(f"{'='*80}\n"))
        
        self.stdout.write(f"URL: {base_url}/servers/getVersion")
        self.stdout.write(f"API Key: {api_key[:15]}...{api_key[-10:]}")
        self.stdout.write(f"API Key Length: {len(api_key)}\n")
        
        # Test 1: Basic request with just the key
        self.stdout.write(self.style.SUCCESS("TEST 1: Authorization header with raw API key"))
        self.stdout.write("-" * 80)
        
        headers = {
            'Authorization': api_key,
            'Accept': 'application/json',
        }
        
        resp = requests.get(
            f'{base_url}/servers/getVersion',
            headers=headers,
            verify=settings.MISP_VERIFY_SSL,
            timeout=10,
            allow_redirects=False
        )
        
        self.stdout.write(f"Status: HTTP {resp.status_code}")
        self.stdout.write(f"Headers sent: {dict(headers)}")
        self.stdout.write(f"Response headers:")
        for k, v in resp.headers.items():
            if k.lower() in ['set-cookie', 'location', 'content-type', 'server']:
                self.stdout.write(f"  {k}: {v}")
        
        self.stdout.write(f"\nResponse body (first 500 chars):")
        self.stdout.write(resp.text[:500])
        
        # Test 2: Try with session
        self.stdout.write(f"\n\n{'='*80}")
        self.stdout.write(self.style.SUCCESS("TEST 2: Using persistent session"))
        self.stdout.write("-" * 80)
        
        session = requests.Session()
        session.headers.update({
            'Authorization': api_key,
            'Accept': 'application/json',
        })
        
        resp2 = session.get(
            f'{base_url}/servers/getVersion',
            verify=settings.MISP_VERIFY_SSL,
            timeout=10,
            allow_redirects=False
        )
        
        self.stdout.write(f"Status: HTTP {resp2.status_code}")
        self.stdout.write(f"Cookies: {session.cookies}")
        self.stdout.write(f"Response body (first 500 chars):")
        self.stdout.write(resp2.text[:500])
        
        # Test 3: Try POST instead of GET
        self.stdout.write(f"\n\n{'='*80}")
        self.stdout.write(self.style.SUCCESS("TEST 3: POST request to /events/add"))
        self.stdout.write("-" * 80)
        
        headers3 = {
            'Authorization': api_key,
            'Content-Type': 'application/json',
        }
        
        payload = {
            'Event': {
                'info': 'Test Event',
                'distribution': 3,
            }
        }
        
        resp3 = requests.post(
            f'{base_url}/events/add',
            headers=headers3,
            json=payload,
            verify=settings.MISP_VERIFY_SSL,
            timeout=10,
            allow_redirects=False
        )
        
        self.stdout.write(f"Status: HTTP {resp3.status_code}")
        self.stdout.write(f"Response body (first 500 chars):")
        self.stdout.write(resp3.text[:500])
        
        # Debug info
        self.stdout.write(f"\n\n{'='*80}")
        self.stdout.write(self.style.WARNING("Debug Information"))
        self.stdout.write("-" * 80)
        self.stdout.write(f"MISP_ENABLED: {settings.MISP_ENABLED}")
        self.stdout.write(f"MISP_URL: {settings.MISP_URL}")
        self.stdout.write(f"MISP_VERIFY_SSL: {settings.MISP_VERIFY_SSL}")
        self.stdout.write(f"API Key is valid format: {len(api_key) == 40}")
        self.stdout.write(f"\nFull API Key being used:")
        self.stdout.write(f"  {api_key}")
        self.stdout.write(f"  Length: {len(api_key)} characters")
        self.stdout.write(f"  First 20 chars: {api_key[:20]}")
        self.stdout.write(f"  Last 20 chars: {api_key[-20:]}")
        
        # Check if this could be a proxy/network issue
        self.stdout.write(f"\n\nPossible Issues:")
        self.stdout.write("1. API key is still incorrect (even though it appears correct)")
        self.stdout.write("2. User account is disabled in MISP")
        self.stdout.write("3. User doesn't have 'API access' permission enabled")
        self.stdout.write("4. There's a network/proxy between container and MISP")
        self.stdout.write("5. MISP configuration requires authentication elsewhere first")
        self.stdout.write("\nNEXT STEPS:")
        self.stdout.write("- Ask MISP admin to verify the user account in: Administration → Users")
        self.stdout.write("- Ensure user is ENABLED and has API access checkbox marked")
        self.stdout.write("- Try logging into MISP web UI with same credentials to verify account works")
        self.stdout.write("- Check if there's a WAF/proxy that might block API requests")
