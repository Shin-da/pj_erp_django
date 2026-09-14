from django.apps import AppConfig


class CatalogueConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalogue"

    def ready(self):
        from . import signals  # noqa: F401
