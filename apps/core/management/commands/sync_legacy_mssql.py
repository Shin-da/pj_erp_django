"""
Pull the latest data from the live iadmin MSSQL server (mssql.tag11.in)
and upsert it into this system.

Safe to run repeatedly and on a schedule (Render Cron Job, Task
Scheduler, whatever) — it never flushes or deletes, and it never writes
back to MSSQL. New rows on the legacy side (new products, items,
resellers, invoices, payments) are created here; rows already imported
are matched by legacy_id and refreshed, except live-system-owned state
(ProductItem.status/location, AssignmentMaster.invoice_status), which is
left alone once set.

Usage:

    python manage.py sync_legacy_mssql
    python manage.py sync_legacy_mssql --dry-run
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.legacy_import import LegacyImporter, WANTED
from apps.core.legacy_mssql import fetch_live_tables


class Command(BaseCommand):
    help = "Sync the latest products/items/resellers/invoices/payments from the live iadmin MSSQL server."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Fetch and report only, no DB writes")
        parser.add_argument("--skip-payments", action="store_true")
        parser.add_argument("--skip-assignments", action="store_true")

    def handle(self, *args, **opts):
        self.stdout.write(
            f"Connecting to legacy MSSQL at {settings.LEGACY_MSSQL_HOST}:{settings.LEGACY_MSSQL_PORT}"
            f"/{settings.LEGACY_MSSQL_DB} ..."
        )
        tables = fetch_live_tables(WANTED, stdout=self.stdout)

        importer = LegacyImporter(stdout=self.stdout)
        importer.run(
            tables,
            flush=False,
            dry_run=opts["dry_run"],
            skip_payments=opts["skip_payments"],
            skip_assignments=opts["skip_assignments"],
        )

        if not opts["dry_run"]:
            self.stdout.write(self.style.SUCCESS(
                f"Live sync complete into {settings.DB_PROFILE} ({settings.DATABASES['default']['NAME']})."
            ))
