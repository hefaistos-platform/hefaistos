from django.apps import AppConfig


class ReviewConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'review'

    def ready(self):
        # Import signals to ensure they are registered when the app is loaded.
        # Avoid circular imports by importing locally.
        import review.signals  # noqa: F401
