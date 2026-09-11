"""
Management command to test MISP configuration and connectivity.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import logging
import json

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test MISP configuration and connectivity'

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO("Testing MISP Configuration..."))
        
        # Check settings
        self.stdout.write(f"\nMISP_ENABLED: {settings.MISP_ENABLED}")
        self.stdout.write(f"MISP_URL: {settings.MISP_URL}")
        self.stdout.write(f"MISP_VERIFY_SSL: {settings.MISP_VERIFY_SSL}")
        self.stdout.write(f"MISP_API_KEY: {settings.MISP_API_KEY[:20]}..." if settings.MISP_API_KEY else "MISP_API_KEY: NOT SET")
        
        if not settings.MISP_ENABLED:
            self.stdout.write(self.style.ERROR("MISP is disabled!"))
            return
        
        if not settings.MISP_URL or not settings.MISP_API_KEY:
            self.stdout.write(self.style.ERROR("MISP_URL or MISP_API_KEY not configured!"))
            return
        
        # Test connection
        try:
            from advops.misp_integration import MISPClient
            self.stdout.write("\nAttempting to connect to MISP...")
            client = MISPClient()
            
            if client.test_connection():
                self.stdout.write(self.style.SUCCESS("✓ MISP connection successful!"))
            else:
                self.stdout.write(self.style.ERROR("✗ MISP connection failed!"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Error: {str(e)}"))
            import traceback
            traceback.print_exc()
        
        # Test event creation
        try:
            self.stdout.write("\nAttempting to create a test event...")
            result = client.create_event(
                event_name="Test Event from HEFAISTOS",
                mitre_patterns=["T1234"],
                attributes=[
                    {'type': 'ip-dst', 'value': '192.168.1.1'},
                    {'type': 'domain', 'value': 'test.example.com'},
                ]
            )
            self.stdout.write(self.style.SUCCESS(f"✓ Test event created successfully!"))
            self.stdout.write(f"Event ID: {result.get('event_id')}")
            self.stdout.write(f"Message: {result.get('message')}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Event creation failed: {str(e)}"))
            import traceback
            traceback.print_exc()

