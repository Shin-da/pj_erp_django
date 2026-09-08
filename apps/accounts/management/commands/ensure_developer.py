"""Create the single developer login. Does not touch other employees."""

import secrets

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.models import Employee

DEFAULT_CODE = "dev"


class Command(BaseCommand):
    help = "Create or update the developer login (employee_code=dev). Ordinary staff are not changed."

    def add_arguments(self, parser):
        parser.add_argument("--code", default=DEFAULT_CODE)
        parser.add_argument("--first-name", default="Jeffmathew")
        parser.add_argument("--last-name", default="Garcia")
        parser.add_argument("--password", default="", help="Set a password. Otherwise a new one is generated.")
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Replace the password even if the account already exists.",
        )

    def handle(self, *args, **opts):
        code = (opts["code"] or DEFAULT_CODE).strip()
        password = (opts["password"] or "").strip()
        first_name = (opts["first_name"] or "Jeffmathew").strip()
        last_name = (opts["last_name"] or "Garcia").strip()
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
        changed_password = created or opts["reset_password"] or bool(opts["password"])
        if changed_password:
            if not password:
                password = secrets.token_urlsafe(12)
            user.set_password(password)
        user.save()
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {code} on {settings.DB_PROFILE} / {settings.DATABASES['default']['NAME']}."
        ))
        if changed_password:
            self.stdout.write(f"Login: {code}")
            self.stdout.write(f"Password: {password}")
        else:
            self.stdout.write("Password left unchanged. Pass --reset-password to issue a new one.")
