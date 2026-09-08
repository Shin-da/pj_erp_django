"""Create the single developer login. Does not touch other employees."""

import logging
import os
import secrets

from django.conf import settings

from apps.accounts.models import Employee

logger = logging.getLogger(__name__)

DEFAULT_CODE = "dev"


def ensure_developer_account(
    *,
    password="",
    code=DEFAULT_CODE,
    first_name="Jeffmathew",
    last_name="Garcia",
    reset_password=False,
    generate_if_missing=False,
):
    """Create or update employee_code `dev` when a password is available.

    Password is read from the argument, then DEV_ACCOUNT_PASSWORD. The value
    is never logged. Returns (user, created, password_set) or (None, False, False)
    when no password was supplied.
    """
    code = (code or DEFAULT_CODE).strip() or DEFAULT_CODE
    password = (password or os.environ.get("DEV_ACCOUNT_PASSWORD") or "").strip()
    first_name = (first_name or "Jeffmathew").strip()
    last_name = (last_name or "Garcia").strip()

    if not password and not generate_if_missing:
        logger.warning("DEV_ACCOUNT_PASSWORD is not set; developer login was not created.")
        print("ensure_developer: skipped (DEV_ACCOUNT_PASSWORD is not set)", flush=True)
        return None, False, False

    user, created = Employee.objects.get_or_create(
        employee_code=code,
        defaults={
            "first_name": first_name,
            "last_name": last_name,
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
            "is_developer": True,
        },
    )
    user.first_name = first_name
    user.last_name = last_name
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.is_developer = True
    password_set = created or reset_password or bool(password)
    if password_set:
        if not password:
            password = secrets.token_urlsafe(12)
        user.set_password(password)
    user.save()
    db_name = settings.DATABASES["default"]["NAME"]
    logger.info(
        "Developer login %s %s on %s/%s (password length %s).",
        code,
        "created" if created else "updated",
        getattr(settings, "DB_PROFILE", "?"),
        db_name,
        len(password) if password_set else 0,
    )
    print(
        "ensure_developer: {verb} {code} on {profile}/{db} (password length {length})".format(
            verb="created" if created else "updated",
            code=code,
            profile=getattr(settings, "DB_PROFILE", "?"),
            db=db_name,
            length=len(password) if password_set else 0,
        ),
        flush=True,
    )
    return user, created, password_set
