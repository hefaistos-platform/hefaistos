from django.apps import AppConfig


class PlaybooksConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'playbooks'

    def ready(self):
        """Import signals when app is ready."""
        import playbooks.signals  # noqa: F401
