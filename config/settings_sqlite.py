"""
Test-only settings: same app configuration, SQLite instead of PostgreSQL.

The app itself is PostgreSQL-only and stays that way — this exists so the
test suite can run on a machine with no local Postgres (both dev laptops
have had a broken local install at some point, and the importer tests are
pure ORM logic that does not care which backend is underneath).

    python manage.py test --settings=config.settings_sqlite

Anything that depends on Postgres-specific behaviour should be tested
against a real Postgres, not here.
"""

from config.settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# WhiteNoise's hashed-manifest storage needs a collectstatic run before any
# template renders. Tests care whether the page renders, not whether the
# CSS filename is fingerprinted.
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
