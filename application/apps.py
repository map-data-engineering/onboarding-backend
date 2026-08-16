from django.apps import AppConfig


class ApplicationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "application"

    def ready(self):
        # Registers the stale-STATIC_ROOT check (application.W001).
        from . import checks  # noqa: F401
