from django.conf import settings


def db_profile(request):
    """Expose which local Postgres catalog this process is using."""
    return {
        "db_profile": settings.DB_PROFILE,
        "db_name": settings.DATABASES["default"]["NAME"],
        "db_is_prod": settings.DB_PROFILE == "prod",
    }
