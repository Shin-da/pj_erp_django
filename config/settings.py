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
    "storages",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
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
    "apps.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
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

# Live legacy iadmin MSSQL server (mssql.tag11.in) — used only by
# `sync_legacy_mssql`, which only ever SELECTs from it.
LEGACY_MSSQL_HOST = config("LEGACY_MSSQL_HOST", default="")
LEGACY_MSSQL_PORT = config("LEGACY_MSSQL_PORT", default="1433")
LEGACY_MSSQL_DB = config("LEGACY_MSSQL_DB", default="")
LEGACY_MSSQL_USER = config("LEGACY_MSSQL_USER", default="")
LEGACY_MSSQL_PASSWORD = config("LEGACY_MSSQL_PASSWORD", default="")

# Shared secret for the free-tier cron trigger (apps/core/views.sync_legacy_webhook),
# pinged by an external scheduler (cron-job.org) instead of a paid Render Cron Job.
SYNC_TRIGGER_TOKEN = config("SYNC_TRIGGER_TOKEN", default="")

# Tiara print sheet. Link must be "anyone with the link can view".
# Sync matches RFID Tag to an existing PJ code and writes purity / weight only.
DATAFILE_SHEET_ID = config("DATAFILE_SHEET_ID", default="1Nme3M7J5mW_cp21uA_nIhDF66xqKMkn9")
DATAFILE_SHEET_GID = config("DATAFILE_SHEET_GID", default="1206911768")

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
# Leading slashes so {% static %} / FileField.url resolve from the site root
# on nested paths (/products/123/), not relative to the current URL.
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Production media: S3-compatible object storage (Cloudflare R2, DigitalOcean
# Spaces, or AWS S3). Set AWS_STORAGE_BUCKET_NAME to enable. Without it,
# uploads stay on local MEDIA_ROOT — fine for runserver; on a Droplet/App
# Platform the disk is ephemeral unless you attach a volume or use Spaces.
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="").strip()
USE_S3_MEDIA = bool(AWS_STORAGE_BUCKET_NAME)

_staticfiles_backend = {
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
}

if USE_S3_MEDIA:
    AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY")
    AWS_S3_ENDPOINT_URL = config("AWS_S3_ENDPOINT_URL", default="").strip() or None
    AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="auto")
    AWS_S3_CUSTOM_DOMAIN = config("AWS_S3_CUSTOM_DOMAIN", default="").strip() or None
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_DEFAULT_ACL = None
    # Public-read bucket / custom domain: False. Private bucket: True (signed URLs).
    AWS_QUERYSTRING_AUTH = config("AWS_QUERYSTRING_AUTH", default=False, cast=bool)
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "public, max-age=86400"}
    AWS_S3_FILE_OVERWRITE = False

    _s3_options = {
        "bucket_name": AWS_STORAGE_BUCKET_NAME,
        "access_key": AWS_ACCESS_KEY_ID,
        "secret_key": AWS_SECRET_ACCESS_KEY,
        "region_name": AWS_S3_REGION_NAME,
        "default_acl": AWS_DEFAULT_ACL,
        "querystring_auth": AWS_QUERYSTRING_AUTH,
        "file_overwrite": AWS_S3_FILE_OVERWRITE,
        "object_parameters": AWS_S3_OBJECT_PARAMETERS,
        "signature_version": AWS_S3_SIGNATURE_VERSION,
    }
    if AWS_S3_ENDPOINT_URL:
        _s3_options["endpoint_url"] = AWS_S3_ENDPOINT_URL
    if AWS_S3_CUSTOM_DOMAIN:
        _s3_options["custom_domain"] = AWS_S3_CUSTOM_DOMAIN
        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"

    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": _s3_options,
        },
        "staticfiles": _staticfiles_backend,
    }
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": _staticfiles_backend,
    }

# Serve MEDIA_ROOT from Django when not on S3. Needed on Render/gunicorn
# (no nginx alias). Dev always; production only if SERVE_MEDIA=True or
# unset while still on local storage (set SERVE_MEDIA=False behind a
# real web-server media alias).
SERVE_MEDIA = config(
    "SERVE_MEDIA",
    default=not USE_S3_MEDIA,
    cast=bool,
)

# Product photo uploads (catalogue /products/photos/). Default keeps the
# original camera file (PRODUCT_PHOTO_MAX_WIDTH=0). Spaces / R2 / S3 store
# the full object; raise DATA_UPLOAD_* if bulk drops hit request limits.
FILE_UPLOAD_MAX_MEMORY_SIZE = config(
    "FILE_UPLOAD_MAX_MEMORY_SIZE",
    default=20 * 1024 * 1024,  # 20 MB in RAM, then spill to temp disk
    cast=int,
)
DATA_UPLOAD_MAX_MEMORY_SIZE = config(
    "DATA_UPLOAD_MAX_MEMORY_SIZE",
    default=220 * 1024 * 1024,  # several large camera JPEGs per POST
    cast=int,
)
PRODUCT_PHOTO_MAX_WIDTH = config("PRODUCT_PHOTO_MAX_WIDTH", default=0, cast=int)
PRODUCT_PHOTO_JPEG_QUALITY = config("PRODUCT_PHOTO_JPEG_QUALITY", default=88, cast=int)
PRODUCT_PHOTO_MAX_UPLOAD_BYTES = config(
    "PRODUCT_PHOTO_MAX_UPLOAD_BYTES",
    default=100 * 1024 * 1024,  # 100 MB per file
    cast=int,
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- External REST API (apps.api) -------------------------------------------
# Deny-by-default. ViewSets also set authentication_classes explicitly.
# Staff HTML login is separate; machine clients use Authorization: Api-Key …
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.authentication.ApiKeyAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.api.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/min",
        "user": "120/min",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "rest_framework.views.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Perfect Jewel ERP API",
    "DESCRIPTION": (
        "Machine-facing read API. Authenticate with "
        "`Authorization: Api-Key <key>` issued by "
        "`python manage.py create_api_client \"<name>\"`."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

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
