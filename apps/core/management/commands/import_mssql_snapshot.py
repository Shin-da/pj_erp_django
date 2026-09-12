"""
Load the FTP MSSQL snapshot (`stock_rfid_backup.sql`) into the current
Postgres catalog, or re-baseline it.

This is a *local* snapshot of production data — never the live tag11.in
server (for that, see `sync_legacy_mssql`, which connects live and is
always safe to re-run). Employee PII (passwords, SSNs, bank details,
salaries) is not imported. What is imported, with real names rather than
placeholder codes:

  - company locations
  - jewellery types + sub-categories
  - currencies / metals / purities / suppliers (from the real lookup tables)
  - product designs + barcodes
  - resellers
  - assignment/invoice headers + barcode lines
  - reseller and supplier payments

Usage (from pj-erp, venv active):

    python manage.py import_mssql_snapshot            # safe: upserts by legacy_id
    python manage.py import_mssql_snapshot --flush     # re-baseline: wipes imported data first

Point at a dump with --dump or LEGACY_SQL_DUMP in .env.

The mapping logic itself lives in apps/core/legacy_import.py, shared with
sync_legacy_mssql so a live connection and a static dump behave identically.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.legacy_sql import parse_dump
from apps.core.legacy_import import LegacyImporter, WANTED, as_str


DEFAULT_DUMP_CANDIDATES = [
    Path(r"C:\Users\Matt\ftp_perfect-jewel-active-sync\iadmin\stock_rfid_backup.sql"),
    Path(r"C:\Users\Matt\ftp_perfect-jewel-active-sync\stock_rfid_backup.sql"),
]


def resolve_dump_path(explicit: str) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise CommandError(f"Dump not found: {p}")
        return p
    env = as_str(getattr(settings, "LEGACY_SQL_DUMP", ""))
    if env:
        p = Path(env)
        if p.exists():
            return p
    for candidate in DEFAULT_DUMP_CANDIDATES:
        if candidate.exists():
            return candidate
    raise CommandError(
        "No MSSQL dump found. Set LEGACY_SQL_DUMP in .env or pass --dump "
        "pointing at stock_rfid_backup.sql from the FTP copy."
    )


class Command(BaseCommand):
    help = "Import the FTP MSSQL stock_rfid snapshot into the current Postgres database."

    def add_arguments(self, parser):
        parser.add_argument("--dump", default="", help="Path to stock_rfid_backup.sql")
        parser.add_argument("--flush", action="store_true", help="Delete previously imported business rows first")
        parser.add_argument("--dry-run", action="store_true", help="Parse and report only, no DB writes")
        parser.add_argument("--skip-payments", action="store_true")
        parser.add_argument("--skip-assignments", action="store_true")

    def handle(self, *args, **opts):
        dump = resolve_dump_path(opts["dump"])
        self.stdout.write(f"Dump: {dump}")
        self.stdout.write(f"Target: {settings.DB_PROFILE} / {settings.DATABASES['default']['NAME']}")
        self.stdout.write("Parsing INSERT rows for lookup + stock + reseller + invoice tables...")

        tables = parse_dump(dump, WANTED, stdout=self.stdout)

        if not tables.get("tblcompany_locations"):
            raise CommandError(
                "Dump parsed but tblcompany_locations is empty. "
                "The file is probably UTF-16 and was read as UTF-8 — re-run after the encoding fix, "
                "or pass --dump at the SSMS script."
            )

        importer = LegacyImporter(stdout=self.stdout)
        importer.run(
            tables,
            flush=opts["flush"],
            dry_run=opts["dry_run"],
            skip_payments=opts["skip_payments"],
            skip_assignments=opts["skip_assignments"],
        )

        if not opts["dry_run"]:
            self.stdout.write(self.style.SUCCESS(
                f"Import complete into {settings.DB_PROFILE} ({settings.DATABASES['default']['NAME']})."
            ))
            self.stdout.write(
                "Not imported (deliberate): employee passwords/SSNs/salaries/bank details, "
                "tracker sessions, transfer history, HR/attendance."
            )
