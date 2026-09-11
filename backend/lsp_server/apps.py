"""
Django application configuration for the lsp_server app.
"""

import logging
import os

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class LspServerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'lsp_server'
    verbose_name = 'SyntaxTide LSP Server'

    def ready(self):
        """Auto-start SyntaxTide LSP servers when the Django application initialises.

        Only runs in the main server process (daphne/runserver) to avoid
        spawning LSP servers during management commands such as migrate or
        collectstatic.
        """
        # `run_backend.py` is the default startup path and already starts LSP servers.
        # Keep app-level autostart opt-in to avoid duplicate bootstrapping/log noise.
        if os.getenv("LSP_AUTOSTART_FROM_APP_READY", "").lower() not in ("1", "true", "yes"):
            return

        # Avoid starting servers during migrations, tests, or management commands
        # that are not the application server.
        _server_commands = {'runserver', 'daphne', 'uvicorn'}
        # Check both the command name in sys.argv (for `python manage.py runserver`)
        # and the basename of sys.argv[0] (for `daphne ...` or `uvicorn ...`).
        import sys
        from pathlib import Path
        argv0_stem = Path(sys.argv[0]).stem if sys.argv else ''
        argv_words = set(sys.argv)
        if not (_server_commands.intersection(argv_words) or argv0_stem in _server_commands):
            return

        # `runserver` starts a reloader parent process; start only in the child.
        if 'runserver' in argv_words and os.getenv('RUN_MAIN') != 'true':
            return

        try:
            from lsp_server.manager import get_lsp_manager
            manager = get_lsp_manager()
            logger.info("Starting SyntaxTide LSP servers…")
            manager.start_all()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to start SyntaxTide LSP servers: %s", exc)
            logger.warning("Continuing without LSP support.")
