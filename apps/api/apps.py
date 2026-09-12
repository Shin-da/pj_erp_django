from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.api"
    verbose_name = "External API"

    def ready(self):
        # Register OpenAPI auth extension for Api-Key documentation.
        from . import spectacular  # noqa: F401

