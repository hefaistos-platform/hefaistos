"""
Django management command to print SyntaxTide LSP status.
"""

from django.core.management.base import BaseCommand

from lsp_server.manager import get_lsp_manager


class Command(BaseCommand):
    help = 'Show SyntaxTide LSP status for all configured languages'

    def handle(self, *args, **options):
        manager = get_lsp_manager()
        status = manager.get_status()

        running_count = sum(1 for info in status.values() if info.get('running'))
        total_count = len(status)

        overall = 'OK' if running_count == total_count else 'DEGRADED'
        self.stdout.write(f"LSP overall status: {overall} ({running_count}/{total_count} running)")

        for language, info in status.items():
            if info.get('running'):
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ {language.upper()} running on port {info.get('port')} (PID: {info.get('pid')})"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"✗ {language.upper()} not running (port {info.get('port')})"
                    )
                )
