"""Restore named label templates. Safe to re-run on every deploy."""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.hardware.saved_layouts import ensure_saved_templates


class Command(BaseCommand):
    help = "Create or restore saved label templates (jefffffff and any others in saved_layouts)."

    def handle(self, *args, **opts):
        results = ensure_saved_templates()
        db = f"{settings.DB_PROFILE} / {settings.DATABASES['default']['NAME']}"
        for tpl, created in results:
            verb = "Created" if created else "Restored"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{verb} {tpl.name!r} (id={tpl.pk}, {tpl.fields.count()} fields) on {db}."
                )
            )
