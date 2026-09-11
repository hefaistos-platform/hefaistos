from django.apps import AppConfig


class MgmtReportsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mgmt_reports'
    verbose_name = 'Management Reports & AI Assistant'

    def ready(self):
        import mgmt_reports.signals  # noqa: F401
