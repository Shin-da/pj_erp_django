"""Create or reset the local admin login (employee_code=1001)."""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.models import Employee

LOCAL_CODE = "1001"
LOCAL_PASSWORD = "changeme123"


class Command(BaseCommand):
    help = "Create or reset local admin employee_code=1001 / changeme123 on the current catalog."

    def handle(self, *args, **opts):
        user, created = Employee.objects.get_or_create(
            employee_code=LOCAL_CODE,
            defaults={
                "first_name": "Local",
                "last_name": "Admin",
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        user.set_password(LOCAL_PASSWORD)
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save()
        verb = "Created" if created else "Reset password for"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {LOCAL_CODE} on {settings.DB_PROFILE} / {settings.DATABASES['default']['NAME']}. "
            f"Password: {LOCAL_PASSWORD}"
        ))
