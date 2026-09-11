"""
Test different MISP API authentication methods and endpoints.
MISP might use different auth header names or endpoint paths.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import requests
import json


class Command(BaseCommand):
    help = 'Test different MISP API authentication methods'

    def handle(self, *args, **options):
        base_url = settings.MISP_URL.rstrip('/')
        if base_url.startswith('http://'):
            base_url = base_url.replace('http://', 'https://', 1)
        
        api_key = settings.MISP_API_KEY
        
        self.stdout.write(self.style.HTTP_INFO(f"\n{'='*80}"))
        self.stdout.write(self.style.HTTP_INFO("MISP API Authentication Method Testing"))
        self.stdout.write(self.style.HTTP_INFO(f"{'='*80}\n"))
        
        self.stdout.write(f"Target URL: {base_url}")
        self.stdout.write(f"API Key: {api_key[:20]}...{api_key[-10:] if len(api_key) > 20 else ''}")
        self.stdout.write(f"API Key Length: {len(api_key)}\n")
        
        # Test different endpoints
        endpoints = [
            '/servers/getVersion',
            '/api/servers/getVersion',
            '/events/add',
            '/api/events/add',
        ]
        
        # Test different header formats
        auth_methods = [
            ('Authorization', api_key, 'Standard Authorization header'),
            ('X-MISP-Auth', api_key, 'X-MISP-Auth header'),
            ('X-API-Key', api_key, 'X-API-Key header'),
            ('Authorization', f'Bearer {api_key}', 'Bearer token format'),
            ('Authorization', f'Token {api_key}', 'Token format'),
        ]
        
        for endpoint in endpoints:
            self.stdout.write(self.style.SUCCESS(f"\n{'='*80}"))
            self.stdout.write(self.style.SUCCESS(f"Testing Endpoint: {endpoint}"))
            self.stdout.write(self.style.SUCCESS(f"{'='*80}\n"))
            
            for header_name, header_value, description in auth_methods:
                headers = {
                    header_name: header_value,
                    'Content-Type': 'application/json',
                }
                
                url = f"{base_url}{endpoint}"
                
                try:
                    resp = requests.get(
                        url,
                        headers=headers,
                        verify=settings.MISP_VERIFY_SSL,
                        timeout=10,
                        allow_redirects=False  # Don't follow redirects to see actual response
                    )
                    
                    # Check response
                    is_html = '<html>' in resp.text.lower() or 'login' in resp.text.lower()
                    is_json = resp.text.strip().startswith('{')
                    
                    status_indicator = self.style.SUCCESS("✓") if is_json and resp.status_code == 200 else self.style.ERROR("✗")
                    
                    self.stdout.write(f"{status_indicator} {description}")
                    self.stdout.write(f"   Status: HTTP {resp.status_code}")
                    
                    if is_html:
                        self.stdout.write(self.style.ERROR(f"   Response: HTML (Login page)"))
                    elif is_json:
                        self.stdout.write(self.style.SUCCESS(f"   Response: JSON ✓"))
                        try:
                            data = resp.json()
                            self.stdout.write(f"   Content: {json.dumps(data, indent=12)[:200]}...")
                        except:
                            pass
                    else:
                        self.stdout.write(f"   Response: {resp.text[:100]}...")
                    
                    if resp.status_code in [301, 302, 307, 308]:
                        self.stdout.write(f"   Redirect to: {resp.headers.get('Location')}")
                    
                    self.stdout.write("")
                    
                except requests.exceptions.Timeout:
                    self.stdout.write(f"✗ {description}")
                    self.stdout.write(f"   TIMEOUT - Server not responding\n")
                except requests.exceptions.ConnectionError as e:
                    self.stdout.write(f"✗ {description}")
                    self.stdout.write(f"   CONNECTION ERROR: {str(e)[:60]}\n")
                except Exception as e:
                    self.stdout.write(f"✗ {description}")
                    self.stdout.write(f"   ERROR: {str(e)[:60]}\n")
        
        self.stdout.write(self.style.WARNING(f"\n{'='*80}"))
        self.stdout.write(self.style.WARNING("Summary:"))
        self.stdout.write(self.style.WARNING(f"{'='*80}\n"))
        self.stdout.write("If you see ✓ with JSON response and HTTP 200:")
        self.stdout.write("  → That's the correct endpoint + auth method combination\n")
        self.stdout.write("If all show HTML (login page):")
        self.stdout.write("  → API key is still not being accepted\n")
        self.stdout.write("If you see 403 or 401:")
        self.stdout.write("  → User doesn't have API permissions in MISP\n")
