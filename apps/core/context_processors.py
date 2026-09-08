from django.conf import settings

from apps.accounts.access import is_developer


def db_profile(request):
    """Expose which catalog this process is using, and whether this login sees /dev/."""
    return {
        "db_profile": settings.DB_PROFILE,
        "db_name": settings.DATABASES["default"]["NAME"],
        "db_is_prod": settings.DB_PROFILE == "prod",
        "show_dev_nav": is_developer(getattr(request, "user", None)),
    }
