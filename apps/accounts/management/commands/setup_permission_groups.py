"""
C2 fix (SYSTEM-AUDIT-2026-09-11.md): seed the three baseline Groups the
owner described — "Vault Staff" (HO/main vault, full operational access),
"Sales / Showroom" (view-only, no extra grants), and "Accounting" (admin
office, higher privilege on the money side).

Idempotent: safe to run again after adding a new permission to
apps/accounts/permissions.py::GROUP_BASELINES — it only ADDS the newly
listed permissions to each Group's baseline, it never removes a
permission an Owner/Admin has since added to the Group by hand, and it
never touches any individual employee's own user_permissions (those are
a per-person override, deliberately outside this command's reach — see
the module docstring in permissions.py).

Usage (once migrate is possible again — see the device_bash / virtiofs
note in whiteboard-notes-2026-09-11-reporting-backlog.md, still broken
as of this writing):

    python manage.py setup_permission_groups
"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.permissions import GROUP_BASELINES


class Command(BaseCommand):
    help = "Create/update the baseline Vault Staff / Sales / Accounting Groups (C2 fix)."

    @transaction.atomic
    def handle(self, *args, **options):
        for group_name, codenames in GROUP_BASELINES.items():
            group, created = Group.objects.get_or_create(name=group_name)
            action = "Created" if created else "Found existing"
            self.stdout.write(f"{action} group '{group_name}'.")

            if not codenames:
                self.stdout.write(f"  (no baseline permissions for '{group_name}' — view-only by design)")
                continue

            resolved = []
            missing = []
            for full_codename in codenames:
                app_label, _, codename = full_codename.partition(".")
                perm = Permission.objects.filter(
                    content_type__app_label=app_label, codename=codename
                ).first()
                if perm:
                    resolved.append(perm)
                else:
                    missing.append(full_codename)

            if resolved:
                group.permissions.add(*resolved)
                self.stdout.write(f"  ensured {len(resolved)} permission(s) on '{group_name}'.")
            if missing:
                self.stdout.write(
                    self.style.WARNING(
                        f"  {len(missing)} permission(s) not found yet (run makemigrations/migrate "
                        f"first, then re-run this command): {', '.join(missing)}"
                    )
                )

        self.stdout.write(self.style.SUCCESS("Done. Individual employee access is still set per-person "
                                              "from Manage Employee Access — this command only seeds group baselines."))
