"""
Load the FTP MSSQL snapshot (`stock_rfid_backup.sql`) into the current
Postgres catalog.

This is a *local* snapshot of production data — never the live tag11.in
server. Employee PII (passwords, SSNs, bank details, salaries) is not
imported. What is imported, with real names rather than placeholder
codes:

  - company locations
  - jewellery types + sub-categories
  - currencies / metals / purities / suppliers (from the real lookup tables)
  - product designs + barcodes
  - resellers
  - assignment/invoice headers + barcode lines
  - reseller and supplier payments

Usage (from pj-erp, venv active):

    python manage.py import_mssql_snapshot --flush

Point at a dump with --dump or LEGACY_SQL_DUMP in .env.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dateutil import parser as date_parser
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.legacy_sql import parse_dump
from apps.core.models import AuditLogEntry
from apps.locations.models import Location, LocationType
from apps.catalogue.models import Category, Currency, Metal, Purity, Supplier, ProductMaster
from apps.inventory.models import ProductItem, StockStatus
from apps.assignment.models import AssignmentMaster, AssignmentLine, Reseller, InvoiceStatus
from apps.payments.models import ResellerPayment, SupplierPayment
from apps.returns.models import ReturnRecord, ReserveAlert
from apps.transfers.models import TransferLine, Transfer
from apps.tracker.models import TrackerScanItem, TrackerSession


WANTED = {
    "tblcompany_locations",
    "tbljewellery_type",
    "tblsub_category_master",
    "tblgeneric_data",
    "tblvendor_type",
    "tblMetalpurity_master",
    "tblproduct_master",
    "tblproduct_detail_master",
    "tblResellerMaster",
    "tblProductAssignMaster",
    "tblProductAssign",
    "tblAssignPayment_transaction",
    "tblproduct_barcode_logs",
    "tblpayment_transaction",
}

LOCATION_TYPE_BY_NID = {
    1: LocationType.HEAD_OFFICE,
    2: LocationType.OTHER,
    3: LocationType.SHOWROOM,
    4: LocationType.PULLOUT,
}

JEWELLERY_TYPE_CODES = {
    "jewellery": "JW",
    "jewelry": "JW",
    "stone": "ST",
    "stones": "ST",
    "finding": "FI",
    "findings": "FI",
    "metal": "MT",
    "metals": "MT",
}

CURRENCY_SYMBOLS = {
    "PHP": "₱",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "HKD": "HK$",
    "SGD": "S$",
    "AUD": "A$",
    "CNY": "¥",
    "RMB": "¥",
}

DEFAULT_DUMP_CANDIDATES = [
    Path(r"C:\Users\Matt\ftp_perfect-jewel-active-sync\iadmin\stock_rfid_backup.sql"),
    Path(r"C:\Users\Matt\ftp_perfect-jewel-active-sync\stock_rfid_backup.sql"),
]


def as_int(val):
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float) and val == int(val):
        return int(val)
    s = str(val).strip()
    if re.match(r"^-?\d+$", s):
        return int(s)
    return None


def as_dec(val):
    if val is None:
        return None
    s = str(val).strip().replace(",", "")
    if s == "" or s.lower() in ("null", "none", "nan"):
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def as_str(val, default=""):
    if val is None:
        return default
    s = str(val).strip()
    return s if s and s.lower() != "null" else default


def as_date(val):
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    try:
        return date_parser.parse(str(val)).date()
    except (ValueError, TypeError, OverflowError):
        return None


def is_active_flag(row):
    status = as_str(row.get("active_status") or row.get("activestatus") or row.get("ActiveStatus")).lower()
    if status in ("inactive", "disable", "disabled", "0", "false"):
        return False
    return True


def split_id_list(val):
    if val is None:
        return []
    return [int(x) for x in re.findall(r"\d+", str(val))]


def jewellery_code(name, code, nid):
    raw = as_str(code).upper().replace(" ", "")
    if raw and len(raw) <= 8:
        return raw[:32]
    key = as_str(name).lower()
    if key in JEWELLERY_TYPE_CODES:
        return JEWELLERY_TYPE_CODES[key]
    return f"JT{nid}"[:32]


def map_item_status(row):
    ics = as_str(row.get("item_current_status")).lower()
    sold = as_str(row.get("sold_status")).lower()
    assign = as_str(row.get("assign_status")).lower()
    reserve = as_str(row.get("reserve_status")).lower()
    if ics in ("sold",) or sold in ("sold", "complete"):
        return StockStatus.SOLD
    if ics in ("reserve", "reserved") or reserve in ("complete", "reserved", "reserve"):
        return StockStatus.RESERVED
    if ics in ("assign", "assigned") or assign in ("complete", "assigned", "assign"):
        return StockStatus.ASSIGNED
    return StockStatus.PENDING


def map_invoice_status(row):
    raw = as_str(row.get("invoice_status") or row.get("invoicestatus")).lower()
    if "cancel" in raw:
        return InvoiceStatus.CANCELLED
    number = as_str(row.get("invoice_number"))
    if raw in ("complete", "completed", "invoiced", "invoice") or number:
        return InvoiceStatus.COMPLETE
    return InvoiceStatus.DRAFT


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
        def rows(name):
            return tables.get(name.lower(), [])

        counts = ", ".join(f"{k}={len(v)}" for k, v in sorted(tables.items()) if v)
        self.stdout.write(f"  {counts or '(no rows parsed)'}")

        if not rows("tblcompany_locations"):
            raise CommandError(
                "Dump parsed but tblcompany_locations is empty. "
                "The file is probably UTF-16 and was read as UTF-8 — re-run after the encoding fix, "
                "or pass --dump at the SSMS script."
            )

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — no database changes."))
            return

        with transaction.atomic():
            if opts["flush"]:
                self._flush()
            location_by_nid = self._import_locations(rows("tblcompany_locations"))
            generic_by_nid = {r["nid"]: r for r in rows("tblgeneric_data") if r.get("nid") is not None}
            category_by_nid = self._import_categories(rows("tbljewellery_type"))
            subcat_by_nid = {
                r["nid"]: as_str(r.get("sub_category")) or f"Sub-category {r['nid']}"
                for r in rows("tblsub_category_master")
                if r.get("nid") is not None
            }
            currency_by_nid = self._import_currencies(generic_by_nid)
            metal_by_nid = self._import_metals(generic_by_nid)
            purity_by_nid = self._import_purities(rows("tblMetalpurity_master"), metal_by_nid)
            supplier_by_nid = self._import_suppliers(rows("tblvendor_type"))
            product_by_nid, product_location = self._import_products(
                rows("tblproduct_master"),
                category_by_nid,
                subcat_by_nid,
                currency_by_nid,
                metal_by_nid,
                purity_by_nid,
                supplier_by_nid,
            )
            item_by_detail_nid, item_by_barcode = self._import_items(
                rows("tblproduct_detail_master"),
                product_by_nid,
                product_location,
                location_by_nid,
            )
            reseller_by_nid = self._import_resellers(rows("tblResellerMaster"))
            if not opts["skip_assignments"]:
                master_by_nid = self._import_assignments(
                    rows("tblProductAssignMaster"),
                    rows("tblProductAssign"),
                    rows("tblproduct_barcode_logs"),
                    rows("tblproduct_detail_master"),
                    reseller_by_nid,
                    item_by_detail_nid,
                    item_by_barcode,
                )
            else:
                master_by_nid = {}
            if not opts["skip_payments"]:
                self._import_reseller_payments(rows("tblAssignPayment_transaction"), master_by_nid)
                self._import_supplier_payments(rows("tblpayment_transaction"), supplier_by_nid, product_by_nid)
            self._ensure_login()

        self.stdout.write(self.style.SUCCESS(
            f"Import complete into {settings.DB_PROFILE} ({settings.DATABASES['default']['NAME']})."
        ))
        self.stdout.write(
            "Not imported (deliberate): employee passwords/SSNs/salaries/bank details, "
            "tracker sessions, transfer history, HR/attendance."
        )

    def _flush(self):
        self.stdout.write("Flushing previously imported business data...")
        AuditLogEntry.objects.all().delete()
        TrackerScanItem.objects.all().delete()
        TrackerSession.objects.all().delete()
        ReserveAlert.objects.all().delete()
        ReturnRecord.objects.all().delete()
        ResellerPayment.objects.all().delete()
        SupplierPayment.objects.all().delete()
        from apps.payments.models import InvoiceCancellation
        InvoiceCancellation.objects.all().delete()
        AssignmentLine.objects.all().delete()
        AssignmentMaster.all_objects.all().delete()
        TransferLine.objects.all().delete()
        Transfer.objects.all().delete()
        ProductItem.objects.all().delete()
        ProductMaster.objects.all().delete()
        Supplier.objects.all().delete()
        Purity.objects.all().delete()
        Metal.objects.all().delete()
        Category.objects.all().delete()
        Currency.objects.all().delete()
        Reseller.objects.all().delete()
        Location.all_objects.all().delete()

    def _import_locations(self, locs):
        by_nid = {}
        for row in locs:
            nid = row["nid"]
            loc, _ = Location.all_objects.update_or_create(
                code=as_str(row.get("location_code")) or f"LOC{nid}",
                defaults={
                    "name": as_str(row.get("location_name")) or f"Location {nid}",
                    "location_type": LOCATION_TYPE_BY_NID.get(nid, LocationType.OTHER),
                    "is_active": is_active_flag(row),
                },
            )
            by_nid[nid] = loc
        self.stdout.write(self.style.SUCCESS(f"  Locations: {len(by_nid)}"))
        return by_nid

    def _import_categories(self, types):
        by_nid = {}
        used_codes = set()
        for row in types:
            nid = row["nid"]
            name = as_str(row.get("jewellery_name")) or f"Type {nid}"
            code = jewellery_code(name, row.get("code"), nid)
            if code in used_codes:
                code = f"{code}{nid}"[:32]
            used_codes.add(code)
            cat, _ = Category.objects.update_or_create(
                code=code,
                defaults={"name": name},
            )
            by_nid[nid] = cat
        fallback, _ = Category.objects.update_or_create(code="UNK", defaults={"name": "Uncategorised"})
        by_nid[None] = fallback
        self.stdout.write(self.style.SUCCESS(f"  Categories (jewellery types): {len(by_nid) - 1}"))
        return by_nid

    def _import_currencies(self, generic_by_nid):
        by_nid = {}
        for nid, row in generic_by_nid.items():
            if as_str(row.get("value_type")).lower() != "currency":
                continue
            code = as_str(row.get("code") or row.get("name")).upper() or f"C{nid}"
            code = code[:10]
            currency, _ = Currency.objects.update_or_create(
                code=code,
                defaults={"symbol": CURRENCY_SYMBOLS.get(code, "")},
            )
            by_nid[nid] = currency
        php, _ = Currency.objects.update_or_create(code="PHP", defaults={"symbol": "₱"})
        if not by_nid:
            self.stdout.write(self.style.WARNING("  Currencies: none in tblgeneric_data; using PHP placeholder"))
        else:
            self.stdout.write(self.style.SUCCESS(f"  Currencies: {len(by_nid)}"))
        by_nid[None] = php
        return by_nid

    def _import_metals(self, generic_by_nid):
        by_nid = {}
        for nid, row in generic_by_nid.items():
            vt = as_str(row.get("value_type")).lower()
            if "metal" not in vt or any(x in vt for x in ("purity", "rate", "country", "weight")):
                continue
            name = as_str(row.get("name") or row.get("code")) or f"Metal {nid}"
            metal, _ = Metal.objects.update_or_create(name=name[:100])
            by_nid[nid] = metal
        self.stdout.write(self.style.SUCCESS(f"  Metals: {len(by_nid)}"))
        return by_nid

    def _import_purities(self, purity_rows, metal_by_nid):
        fallback_metal = next(iter(metal_by_nid.values()), None)
        if fallback_metal is None:
            fallback_metal, _ = Metal.objects.get_or_create(name="Unspecified")
        by_nid = {}
        for row in purity_rows:
            nid = row["nid"]
            name = as_str(row.get("Metalpurity") or row.get("metalpurity")) or f"Purity {nid}"
            purity, _ = Purity.objects.update_or_create(
                metal=fallback_metal,
                name=name[:50],
            )
            by_nid[nid] = purity
        self.stdout.write(self.style.SUCCESS(f"  Purities: {len(by_nid)}"))
        return by_nid

    def _import_suppliers(self, vendors):
        by_nid = {}
        for row in vendors:
            nid = row["nid"]
            name = as_str(row.get("c_name") or row.get("name")) or f"Vendor {nid}"
            sup, _ = Supplier.objects.update_or_create(
                reference_code=str(nid),
                defaults={"name": name[:150]},
            )
            by_nid[nid] = sup
            by_nid[str(nid)] = sup
        self.stdout.write(self.style.SUCCESS(f"  Suppliers: {len(vendors)}"))
        return by_nid

    def _import_products(
        self, products, category_by_nid, subcat_by_nid, currency_by_nid,
        metal_by_nid, purity_by_nid, supplier_by_nid,
    ):
        fallback_cat = category_by_nid[None]
        fallback_cur = currency_by_nid[None]
        objs = []
        nids = []
        locations = []
        for row in products:
            nid = row["nid"]
            cat = category_by_nid.get(as_int(row.get("category")), fallback_cat)
            sub_name = subcat_by_nid.get(as_int(row.get("sub_category")), "")
            currency = currency_by_nid.get(as_int(row.get("CurrencyType")), fallback_cur)
            metal = metal_by_nid.get(as_int(row.get("metal")))
            purity = purity_by_nid.get(as_int(row.get("metal_purity_id")))
            if purity and metal and purity.metal_id != metal.pk:
                purity, _ = Purity.objects.get_or_create(metal=metal, name=purity.name)
            supplier = supplier_by_nid.get(as_int(row.get("vendor_id"))) or supplier_by_nid.get(as_str(row.get("vendor_id")))
            objs.append(ProductMaster(
                reference_id=as_str(row.get("reference_id"))[:100],
                name=(as_str(row.get("product_Name")) or f"Legacy item {nid}")[:200],
                category=cat,
                subcategory=sub_name[:100],
                currency=currency,
                metal=metal,
                purity=purity,
                supplier=supplier,
                net_weight=as_dec(row.get("net_wt")),
                gross_weight=as_dec(row.get("gross_wt")),
                purchase_price=as_dec(row.get("purchase_price")) or as_dec(row.get("actual_price")),
                selling_price=as_dec(row.get("selling_price")),
                is_active=is_active_flag(row),
            ))
            nids.append(nid)
            locations.append(as_int(row.get("company_locationid")))
        created = ProductMaster.objects.bulk_create(objs, batch_size=500)
        product_by_nid = dict(zip(nids, created))
        product_location = dict(zip(nids, locations))
        self.stdout.write(self.style.SUCCESS(f"  ProductMaster: {len(created)}"))
        return product_by_nid, product_location

    def _import_items(self, details, product_by_nid, product_location, location_by_nid):
        default_loc = location_by_nid.get(1) or next(iter(location_by_nid.values()), None)
        if default_loc is None:
            raise CommandError("No locations imported — cannot attach items.")
        objs = []
        detail_nids = []
        seen_barcodes = set()
        skipped = 0
        for row in details:
            pmid = as_int(row.get("product_masterid"))
            product = product_by_nid.get(pmid)
            barcode = as_str(row.get("barcode_number"))
            if product is None or not barcode or barcode in seen_barcodes:
                skipped += 1
                continue
            seen_barcodes.add(barcode)
            loc_id = product_location.get(pmid)
            loc = location_by_nid.get(loc_id, default_loc)
            reprint = "PRINTED" if as_str(row.get("barcode_reprint_status")).lower() == "complete" else "NONE"
            objs.append(ProductItem(
                barcode=barcode[:100],
                product=product,
                location=loc,
                status=map_item_status(row),
                reprint_status=reprint,
            ))
            detail_nids.append(row["nid"])
        created = ProductItem.objects.bulk_create(objs, batch_size=500)
        item_by_detail_nid = dict(zip(detail_nids, created))
        item_by_barcode = {item.barcode: item for item in created}
        self.stdout.write(self.style.SUCCESS(
            f"  ProductItem: {len(created)} created, {skipped} skipped (missing product/barcode/duplicate)"
        ))
        return item_by_detail_nid, item_by_barcode

    def _import_resellers(self, resellers):
        by_nid = {}
        for row in resellers:
            nid = row["nid"]
            name = as_str(row.get("company_name") or row.get("name")) or f"Reseller {nid}"
            obj, _ = Reseller.objects.update_or_create(
                reference_code=str(nid),
                defaults={
                    "name": name[:150],
                    "is_active": is_active_flag(row),
                },
            )
            by_nid[nid] = obj
            by_nid[str(nid)] = obj
        self.stdout.write(self.style.SUCCESS(f"  Resellers: {len(resellers)}"))
        return by_nid

    def _import_assignments(
        self, masters, lines, barcode_logs, details,
        reseller_by_nid, item_by_detail_nid, item_by_barcode,
    ):
        logs_by_assign = {}
        for row in barcode_logs:
            aid = as_int(row.get("assign_detail_id"))
            if aid is None:
                continue
            logs_by_assign.setdefault(aid, []).append(row)

        details_by_assign = {}
        for row in details:
            aid = as_int(row.get("assignid"))
            if aid is None:
                continue
            details_by_assign.setdefault(aid, []).append(row)

        master_by_nid = {}
        skipped_masters = 0
        for row in masters:
            nid = row["nid"]
            reseller = reseller_by_nid.get(as_int(row.get("reseller_id"))) or reseller_by_nid.get(as_str(row.get("reseller_id")))
            if reseller is None:
                skipped_masters += 1
                continue
            inv = as_str(row.get("invoice_number") or row.get("invoice_name"))
            is_reserve = inv.upper().startswith("RN") or as_str(row.get("invoice_name")).upper().startswith("RN")
            am = AssignmentMaster(
                reseller=reseller,
                is_reserve=is_reserve,
                invoice_status=map_invoice_status(row),
                invoice_number=inv[:32],
            )
            am.save()
            master_by_nid[nid] = am
            master_by_nid[str(nid)] = am

        line_objs = []
        seen_pairs = set()
        skipped_lines = 0

        def add_line(master, item, unit_price):
            pair = (master.pk, item.pk)
            if pair in seen_pairs:
                return
            seen_pairs.add(pair)
            line_objs.append(AssignmentLine(
                master=master,
                item=item,
                unit_price=unit_price if unit_price is not None else Decimal("0"),
            ))

        for row in lines:
            master = master_by_nid.get(as_int(row.get("master_id"))) or master_by_nid.get(as_str(row.get("master_id")))
            if master is None:
                skipped_lines += 1
                continue
            price = as_dec(row.get("selling_price")) or as_dec(row.get("return_price"))
            items_for_line = []
            for log in logs_by_assign.get(row["nid"], []):
                barcode = as_str(log.get("barcode"))
                item = item_by_barcode.get(barcode)
                if item:
                    items_for_line.append(item)
            if not items_for_line:
                for det in details_by_assign.get(row["nid"], []):
                    item = item_by_detail_nid.get(det["nid"])
                    if item:
                        items_for_line.append(item)
            if not items_for_line:
                for det_nid in split_id_list(row.get("barcode_nid")):
                    item = item_by_detail_nid.get(det_nid)
                    if item:
                        items_for_line.append(item)
            if not items_for_line:
                skipped_lines += 1
                continue
            for item in items_for_line:
                add_line(master, item, price)

        AssignmentLine.objects.bulk_create(line_objs, batch_size=500, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(
            f"  AssignmentMaster: {len(masters) - skipped_masters} "
            f"({skipped_masters} skipped, no reseller)  "
            f"AssignmentLine: {len(line_objs)} ({skipped_lines} assign-rows with no barcode)"
        ))
        return master_by_nid

    def _import_reseller_payments(self, payments, master_by_nid):
        objs = []
        skipped = 0
        for row in payments:
            master = master_by_nid.get(as_int(row.get("assign_masterid"))) or master_by_nid.get(as_str(row.get("assign_masterid")))
            amount = as_dec(row.get("paid_amount")) or as_dec(row.get("total_amount"))
            if master is None or amount is None:
                skipped += 1
                continue
            paid_on = as_date(row.get("credit_date") or row.get("creationdate")) or timezone.now().date()
            note = " ".join(filter(None, [
                as_str(row.get("transaction_number")),
                as_str(row.get("py_number")),
                as_str(row.get("pay_mode")),
            ]))[:255]
            objs.append(ResellerPayment(
                assignment=master,
                amount=amount,
                paid_on=paid_on,
                reference_note=note,
            ))
        ResellerPayment.objects.bulk_create(objs, batch_size=500)
        self.stdout.write(self.style.SUCCESS(f"  ResellerPayment: {len(objs)} ({skipped} skipped)"))

    def _import_supplier_payments(self, payments, supplier_by_nid, product_by_nid):
        objs = []
        skipped = 0
        for row in payments:
            supplier = supplier_by_nid.get(as_int(row.get("vender_id"))) or supplier_by_nid.get(as_str(row.get("vender_id")))
            amount = as_dec(row.get("paid_amount")) or as_dec(row.get("total_amount"))
            if supplier is None or amount is None:
                skipped += 1
                continue
            product = product_by_nid.get(as_int(row.get("product_id")))
            paid_on = as_date(row.get("credit_date") or row.get("creationdate")) or timezone.now().date()
            note = " ".join(filter(None, [
                as_str(row.get("transaction_number")),
                as_str(row.get("py_number")),
                as_str(row.get("pay_mode")),
            ]))[:255]
            objs.append(SupplierPayment(
                supplier=supplier,
                product=product,
                amount=amount,
                paid_on=paid_on,
                reference_note=note,
            ))
        SupplierPayment.objects.bulk_create(objs, batch_size=500)
        self.stdout.write(self.style.SUCCESS(f"  SupplierPayment: {len(objs)} ({skipped} skipped)"))

    def _ensure_login(self):
        from django.core.management import call_command
        call_command("ensure_local_admin")
