"""
Interactive guide for setting up and verifying MISP integration.
Run this command to step through the setup process.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import requests


class Command(BaseCommand):
    help = 'Interactive guide for MISP setup and verification'

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO(f"\n{'='*80}"))
        self.stdout.write(self.style.HTTP_INFO("HEFAISTOS MISP INTEGRATION SETUP GUIDE"))
        self.stdout.write(self.style.HTTP_INFO(f"{'='*80}\n"))

        # Check MISP configuration
        self.stdout.write(self.style.SUCCESS("1️⃣  CHECKING CONFIGURATION"))
        self.stdout.write(f"   MISP_ENABLED: {settings.MISP_ENABLED}")
        self.stdout.write(f"   MISP_URL: {settings.MISP_URL}")
        self.stdout.write(f"   MISP_VERIFY_SSL: {settings.MISP_VERIFY_SSL}")
        self.stdout.write(f"   API Key Set: {'Yes' if settings.MISP_API_KEY else 'No'}")
        if settings.MISP_API_KEY:
            self.stdout.write(f"   API Key Length: {len(settings.MISP_API_KEY)} characters")
            self.stdout.write(f"   API Key (masked): {settings.MISP_API_KEY[:10]}...{settings.MISP_API_KEY[-10:]}\n")
        else:
            self.stdout.write(self.style.ERROR("   ❌ MISP_API_KEY not set!\n"))

        if not settings.MISP_ENABLED:
            self.stdout.write(self.style.ERROR("   ❌ MISP is disabled!\n"))
            self.stdout.write("   To enable MISP:")
            self.stdout.write("   1. Set MISP_ENABLED=true in your configuration")
            self.stdout.write("   2. Set MISP_URL to your MISP server URL")
            self.stdout.write("   3. Set MISP_API_KEY to your API key\n")
            return

        # Test connectivity
        self.stdout.write(self.style.SUCCESS("2️⃣  TESTING MISP SERVER CONNECTIVITY"))
        try:
            base_url = settings.MISP_URL.rstrip('/')
            if base_url.startswith('http://'):
                base_url = base_url.replace('http://', 'https://', 1)
            
            resp = requests.get(
                f'{base_url}/servers/getVersion',
                timeout=5,
                verify=settings.MISP_VERIFY_SSL,
                allow_redirects=False  # Don't follow redirects yet
            )
            
            if resp.status_code == 301:
                self.stdout.write(f"   HTTP → HTTPS redirect detected (status {resp.status_code})")
                self.stdout.write(f"   Redirecting to: {resp.headers.get('Location')}")
                self.stdout.write("   ✓ This is expected behavior\n")
            elif resp.status_code == 200:
                self.stdout.write(f"   ✓ Server is accessible (HTTP {resp.status_code})\n")
            else:
                self.stdout.write(f"   ! Server returned HTTP {resp.status_code}\n")

        except requests.exceptions.Timeout:
            self.stdout.write("   ❌ Timeout - MISP server not responding")
            self.stdout.write("   Check: Is MISP running? Is the URL correct?\n")
            return
        except requests.exceptions.ConnectionError as e:
            self.stdout.write(f"   ❌ Connection failed: {str(e)[:60]}")
            self.stdout.write("   Check: Can you reach the MISP server from here?\n")
            return

        # Test authentication
        self.stdout.write(self.style.SUCCESS("3️⃣  TESTING MISP AUTHENTICATION"))
        base_url = settings.MISP_URL.rstrip('/')
        if base_url.startswith('http://'):
            base_url = base_url.replace('http://', 'https://', 1)
        
        headers = {
            'Authorization': settings.MISP_API_KEY,
            'Content-Type': 'application/json',
        }
        
        resp = requests.get(
            f'{base_url}/servers/getVersion',
            headers=headers,
            verify=settings.MISP_VERIFY_SSL,
            timeout=5,
            allow_redirects=True
        )
        
        self.stdout.write(f"   Response Status: HTTP {resp.status_code}\n")
        
        if resp.status_code == 200 and resp.text.startswith('{'):
            self.stdout.write(self.style.SUCCESS("   ✅ AUTHENTICATION SUCCESSFUL!\n"))
            try:
                import json
                data = resp.json()
                self.stdout.write(f"   MISP Version: {data.get('version', 'unknown')}")
                self.stdout.write(f"   MISP Status: OK\n")
            except:
                pass
        elif resp.status_code == 302 or '<html>' in resp.text.lower():
            self.stdout.write(self.style.ERROR("   ❌ AUTHENTICATION FAILED!\n"))
            self.stdout.write("   The API key is not valid or the user lacks API permissions.\n")
            self.stdout.write(self.style.WARNING("   📋 NEXT STEPS:\n"))
            self.stdout.write("   1. Open MISP in your browser: https://misp.counterintel.cz")
            self.stdout.write("   2. Log in with your MISP credentials")
            self.stdout.write("   3. Click your username → Profile")
            self.stdout.write("   4. Copy the 'Authkey' field (not your password!)")
            self.stdout.write("   5. Update MISP_API_KEY with the correct authkey")
            self.stdout.write("   6. Restart backend: docker compose restart backend")
            self.stdout.write("   7. Run this guide again to verify\n")
        elif resp.status_code in [401, 403]:
            self.stdout.write(self.style.ERROR(f"   ❌ HTTP {resp.status_code} - Access Denied\n"))
            self.stdout.write("   Possible causes:")
            self.stdout.write("   - Invalid API key")
            self.stdout.write("   - User account is disabled")
            self.stdout.write("   - User doesn't have API permissions\n")
            self.stdout.write("   Check with your MISP administrator.\n")
        else:
            self.stdout.write(f"   ! Unexpected response\n")

        # Summary
        self.stdout.write(self.style.SUCCESS("4️⃣  SUMMARY\n"))
        self.stdout.write("   Helpful commands:")
        self.stdout.write("   - Test API key: docker compose exec backend python manage.py test_misp_key --key YOUR_KEY")
        self.stdout.write("   - Verify connection: docker compose exec backend python manage.py test_misp")
        self.stdout.write("   - Detailed diagnostics: docker compose exec backend python manage.py test_misp_diagnostic\n")
        
        self.stdout.write("   Troubleshooting:")
        self.stdout.write("   - See Docs/MISP_API_KEY_VERIFICATION.md for detailed instructions")
        self.stdout.write("   - Check backend logs: docker compose logs backend -f\n")

        self.stdout.write(f"{'='*80}\n")
