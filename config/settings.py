"""
Django settings for the Perfect Jewel ERP rebuild (config project).

Replaces `ftp_perfect-jewel-active-sync` (ASP.NET Web Forms / SQL Server).
See project doc `perfect-jewel-system-landscape.md` for the full rationale
and REBUILD-ARCHITECTURE-AND-BUDGET.md for the architecture this scaffold
implements.
"""

from pathlib import Path

from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("DJANGO_SECRET_KEY", default="dev-only-insecure-key-change-me")
DEBUG = config("DJANGO_DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django_q",
    # Perfect Jewel apps — order matters somewhat for migration dependency
    # readability, not for Django itself.
    "apps.core",
    "apps.accounts",
    "apps.locations",
    "apps.catalogue",
    "apps.inventory",
    "apps.transfers",
    "apps.tracker",
    "apps.assignment",
    "apps.payments",
    "apps.returns",
    "apps.hardware",
    "apps.sync",
    "apps.hr",
    "apps.reporting",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.db_profile",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database ---------------------------------------------------------------
# PostgreSQL only. The legacy system's biggest structural gap was 0 foreign
# keys / 0 indexes on core tables (confirmed by the SYSTEM-AUDIT.md audit) —
# this is the one thing this rebuild is not allowed to compromise on.
#
# Two local catalogs, switched by DJANGO_DB_PROFILE (never the live MSSQL
# host). Both are filled from the same FTP snapshot of stock_rfid:
#   dev  -> pj_erp_dev   working copy you can mutate while building
#   prod -> pj_erp_prod  frozen snapshot of real catalogue/resellers/invoices
# Flip DJANGO_DB_PROFILE in .env and restart runserver. Same credentials.

DB_PROFILE = config("DJANGO_DB_PROFILE", default="dev").strip().lower()
if DB_PROFILE not in ("dev", "prod"):
    raise ImproperlyConfigured(
        f"DJANGO_DB_PROFILE must be 'dev' or 'prod', got {DB_PROFILE!r}"
    )

DB_NAME_BY_PROFILE = {
    "dev": config("DB_NAME_DEV", default="pj_erp_dev"),
    "prod": config("DB_NAME_PROD", default="pj_erp_prod"),
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": DB_NAME_BY_PROFILE[DB_PROFILE],
        "USER": config("DB_USER", default="pj_dev"),
        "PASSWORD": config("DB_PASSWORD", default="pj_dev_local"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
    }
}

# Path to the MSSQL script dump (schema + INSERTs) taken from the FTP
# stock_rfid snapshot. Used by `import_mssql_snapshot`. Never commit it.
LEGACY_SQL_DUMP = config("LEGACY_SQL_DUMP", default="")

# --- Auth --------------------------------------------------------------------
# Custom user model from day one — never swap this in later, Django makes it
# very painful to change after the first migration. Replaces tblemployee's
# plaintext `password` column and the CSV-role-matched-with-LIKE permission
# model in previliege.aspx / validateuserrole.

AUTH_USER_MODEL = "accounts.Employee"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"

# --- I18N ----------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = config("DJANGO_TIME_ZONE", default="Asia/Manila")
USE_I18N = True
USE_TZ = True

# --- Static / media --------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Background jobs (Tiara/Irys sync, etc.) --------------------------------
# django-q2 over the ORM as a broker for now — no Redis dependency to stand
# up for a single-VPS deployment this size. Swap the broker later if the
# workload ever needs it. Explicit dry-run flag lives on apps.sync's job
# model itself, not implied by a global setting, so a stray call can't
# accidentally fire a live Tiara push.
Q_CLUSTER = {
    "name": "pj_erp",
    "workers": 2,
    "recycle": 500,
    "timeout": 120,
    "retry": 180,
    "queue_limit": 50,
    "bulk": 10,
    "orm": "default",
}

# --- Logging -----------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
