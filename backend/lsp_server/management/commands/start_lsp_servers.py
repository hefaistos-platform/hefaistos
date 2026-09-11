"""
Django management command to start SyntaxTide LSP servers
"""

from django.core.management.base import BaseCommand
from lsp_server.manager import get_lsp_manager


class Command(BaseCommand):
    help = 'Start SyntaxTide LSP servers for detection rule editing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--language',
            type=str,
            choices=['kql', 'spl', 'wazuh', 'aql', 'all'],
            default='all',
            help='Language server to start (default: all)',
        )

    def handle(self, *args, **options):
        manager = get_lsp_manager()
        language = options['language']

        if language == 'all':
            self.stdout.write("Starting all LSP servers...")
            manager.start_all()
        else:
            self.stdout.write(f"Starting LSP server for {language}...")
            manager.start_lsp_server(language)

        # Print status
        status = manager.get_status()
        for lang, info in status.items():
            if info['running']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ {lang.upper()} LSP server running on port {info['port']} (PID: {info['pid']})"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"✗ {lang.upper()} LSP server not running")
                )
