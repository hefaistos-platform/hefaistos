"""
Quick diagnostic to show where MISP API key comes from and what its current value is.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import os


class Command(BaseCommand):
    help = 'Show MISP API key source and current value'

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO(f"\n{'='*70}"))
        self.stdout.write(self.style.HTTP_INFO("MISP API KEY SOURCE DIAGNOSIS"))
        self.stdout.write(self.style.HTTP_INFO(f"{'='*70}\n"))

        # Check possible sources
        self.stdout.write(self.style.SUCCESS("Checking API Key Sources:\n"))

        # Source 1: Docker/Kubernetes secret
        docker_secret = "/run/secrets/misp_key"
        try:
            with open(docker_secret, 'r') as f:
                docker_value = f.read().strip()
            self.stdout.write(f"1. Docker secret (/run/secrets/misp_key):")
            self.stdout.write(f"   ✓ File exists")
            self.stdout.write(f"   Content: '{docker_value}'")
            if docker_value == "PLACEHOLDER_API_KEY_REPLACE_ME" or docker_value == "MISP Key":
                self.stdout.write(self.style.ERROR(f"   ❌ PLACEHOLDER - NEEDS UPDATE!\n"))
            elif len(docker_value) == 40:
                self.stdout.write(self.style.SUCCESS(f"   ✓ Looks like valid API key (40 chars)\n"))
            else:
                self.stdout.write(self.style.WARNING(f"   ⚠️  Unusual length: {len(docker_value)} chars\n"))
        except FileNotFoundError:
            self.stdout.write(f"1. Docker secret (/run/secrets/misp_key):")
            self.stdout.write(f"   ✗ File not found (not in Docker/K8s)\n")

        # Source 2: Environment variable
        env_value = os.environ.get('MISP_API_KEY')
        self.stdout.write(f"2. Environment variable (MISP_API_KEY):")
        if env_value:
            self.stdout.write(f"   ✓ Set in environment")
            if len(env_value) > 20:
                masked = env_value[:10] + "***" + env_value[-5:]
            else:
                masked = env_value
            self.stdout.write(f"   Value: {masked}")
            if env_value == "PLACEHOLDER_API_KEY_REPLACE_ME" or "KEY" in env_value.upper():
                self.stdout.write(self.style.ERROR(f"   ❌ PLACEHOLDER - NEEDS UPDATE!\n"))
            elif len(env_value) == 40:
                self.stdout.write(self.style.SUCCESS(f"   ✓ Looks like valid API key\n"))
            else:
                self.stdout.write(self.style.WARNING(f"   ⚠️  Unusual length: {len(env_value)} chars\n"))
        else:
            self.stdout.write(f"   ✗ Not set in environment\n")

        # Currently loaded value
        self.stdout.write(f"3. Currently loaded value (in Django settings):")
        if settings.MISP_API_KEY:
            current_masked = settings.MISP_API_KEY[:10] + "***" + settings.MISP_API_KEY[-5:]
            self.stdout.write(f"   ✓ Value loaded: {current_masked}")
            self.stdout.write(f"   Length: {len(settings.MISP_API_KEY)} chars")
            if settings.MISP_API_KEY == "PLACEHOLDER_API_KEY_REPLACE_ME" or "KEY" in settings.MISP_API_KEY.upper():
                self.stdout.write(self.style.ERROR(f"   ❌ THIS IS A PLACEHOLDER!\n"))
            elif len(settings.MISP_API_KEY) == 40:
                self.stdout.write(self.style.SUCCESS(f"   ✓ Appears to be valid API key\n"))
        else:
            self.stdout.write(self.style.ERROR(f"   ❌ NO API KEY LOADED!\n"))

        # Summary
        self.stdout.write(self.style.SUCCESS("Summary:\n"))
        if settings.MISP_API_KEY and len(settings.MISP_API_KEY) == 40 and "PLACEHOLDER" not in settings.MISP_API_KEY:
            self.stdout.write(self.style.SUCCESS("✓ API Key appears to be valid and loaded correctly.\n"))
            self.stdout.write("Did you remember to restart the backend after updating?")
            self.stdout.write("Run: docker compose restart backend\n")
        else:
            self.stdout.write(self.style.ERROR("❌ API Key is NOT properly configured!\n"))
            self.stdout.write("TO FIX:\n")
            self.stdout.write("1. Get your MISP Authkey from user profile")
            self.stdout.write("2. Update .secrets/misp_key with the correct key (40 chars)")
            self.stdout.write("   OR set MISP_API_KEY environment variable")
            self.stdout.write("3. Restart backend: docker compose restart backend\n")
            self.stdout.write("Current key is:")
            self.stdout.write(f"  '{settings.MISP_API_KEY}' ({len(settings.MISP_API_KEY) if settings.MISP_API_KEY else 0} chars)\n")

        self.stdout.write(f"{'='*70}\n")
