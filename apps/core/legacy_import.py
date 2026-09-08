"""
Shared legacy-data import/sync logic.

Used by two management commands:
  - `import_mssql_snapshot` — reads a static .sql dump (one-time / re-baseline)
  - `sync_legacy_mssql` — reads live from mssql.tag11.in (recurring, safe)

Both hand this module the same shape of data: {table_name: [row dict, ...]}
with table names lowercased and row dict keys matching the original SQL
Server column names (see apps/core/legacy_sql.py's parse_dump and
apps/core/legacy_mssql.py's fetch_live_tables).

Idempotency: every row that has a stable legacy primary key (`nid` in the
source system) is upserted by a `legacy_id` field on the Django side
(ProductMaster, ProductItem, AssignmentMaster, ResellerPayment,
SupplierPayment; Reseller/ResellerLocation already had this). Re-running
an import never creates duplicates.

Ownership boundary on re-sync: iadmin is the book of record. Every field,
including state the Django app can also change (ProductItem.status and
location, AssignmentMaster.invoice_status), is refreshed from iadmin on
every run.

This used to be the other way round — those three fields were skipped on
update, on the theory that a staffer might have changed them here. In
practice nobody works in this system yet, so the effect was a dashboard
that silently drifted: on 9 Sep 2026 iadmin showed 577 pieces sold and
7,387 in company stock while this system, syncing daily from the same
server, still showed 337 and 7,626. New pieces arrived; the status of
existing pieces never moved again after first import. Same story for
location, which additionally read the *master* row's `company_locationid`
(the shared design record) instead of the per-barcode one, so 6,646
pieces sat at Head Office here while iadmin had them spread across Main
Vault, Pullout and the showroom.

Pass `preserve_local_state=True` to get the old behaviour back. That is
the correct setting on the day Perfect Jewel starts entering work here
instead of in iadmin, and the wrong one until then.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from dateutil import parser as date_parser
from django.core.management.base import CommandError
from django.core.management.color import color_style
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import AuditLogEntry
from apps.locations.models import Location, LocationType
from apps.catalogue.models import (
    Category, Currency, Metal, Purity, Supplier, ProductMaster, strip_dflt_prefix,
)
from apps.inventory.models import ProductItem, StockStatus
from apps.assignment.models import (
    AssignmentMaster,
    AssignmentLine,
    InvoiceStatus,
    Reseller,
    ResellerLocation,
)
from apps.payments.models import ResellerPayment, SupplierPayment, InvoiceCancellation
from apps.returns.models import ReturnRecord, ReserveAlert
from apps.transfers.models import TransferLine, Transfer, TransferStatus
from apps.tracker.models import ScanMode, ScanResult, TrackerScanItem, TrackerSession


WANTED = {
    "tblcompany_locations",
    "tbljewellery_type",
    "tblsub_category_master",
    "tblgeneric_data",
    "tblvendor_type",
    "tblMetalpurity_master",
    "tblproduct_master",
    "tblproduct_detail_master",
    "tbljewellery_metal_details",
    "tblmetalcountry_master",
    "tblpurity_country_mgmt",
    "tbljewellery_stone_details",
    "tblstone_sub_category",
    "tblResellerMaster",
    "tblresellerlocationMaster",
    "tblProductAssignMaster",
    "tblProductAssign",
    "tblAssignPayment_transaction",
    "tblproduct_barcode_logs",
    "tblpayment_transaction",
    "tblproduct_transfer",
    "tblproduct_transfer_details",
    "tblproduct_tracker",
    "tblproduct_tracker_itemsdeatils",
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


def as_aware(val):
    """Legacy datetimes are naive local time; `created_at` columns are not."""
    if isinstance(val, date) and not isinstance(val, datetime):
        val = datetime.combine(val, datetime.min.time())
    if not isinstance(val, datetime):
        return None
    if timezone.is_naive(val):
        return timezone.make_aware(val, timezone.get_default_timezone())
    return val


def is_visible_row(row):
    """`bstatus` 0 means the legacy row was soft-deleted / hidden."""
    val = as_int(row.get("bstatus"))
    return val != 0


def map_transfer_status(row):
    """
    A legacy transfer row is history, not a to-do.

    `tblproduct_transfer.return_status` defaults to `'pending'` and no
    stored procedure ever moves it off that value — the return-transfer
    button in `ProductTransferList.aspx.cs` was commented out and never
    finished (INVENTORY-AND-INVOICING.md §4.5). The stock itself was
    already moved at transfer time. Importing those rows as PENDING is
    what makes the legacy dashboard advertise "291 active transfers" when
    nothing is in transit, so they land here as COMPLETE unless the row
    actually says it came back.
    """
    raw = as_str(row.get("return_status")).lower()
    if raw.startswith("return") or raw in ("complete", "completed", "done"):
        return TransferStatus.RETURNED
    return TransferStatus.COMPLETE


def map_scan_mode(row):
    raw = as_str(row.get("scan_mode")).lower()
    if raw.startswith("open"):
        return ScanMode.OPENING
    if raw.startswith("clos"):
        return ScanMode.CLOSING
    if raw.startswith("find"):
        return ScanMode.FIND
    if raw.startswith("check"):
        return ScanMode.CHECK
    if "transfer" in as_str(row.get("workflow_mode")).lower():
        return ScanMode.TRANSFER
    return ScanMode.CHECK


SCAN_RESULT_BY_LEGACY_LOCATION = {
    "company": ScanResult.COMPANY_STOCK,
    "assign": ScanResult.ASSIGNED,
    "assigned": ScanResult.ASSIGNED,
    "sold": ScanResult.SOLD,
    "reserve": ScanResult.RESERVED,
    "reserved": ScanResult.RESERVED,
    "loss": ScanResult.LOSS,
    "elsewhere": ScanResult.ELSEWHERE,
}


class LegacyImporter:
    """Maps parsed/fetched legacy rows onto the Django schema."""

    def __init__(self, stdout):
        self.stdout = stdout
        self.style = color_style()

    def run(
        self, tables, *, flush=False, dry_run=False, skip_payments=False,
        skip_assignments=False, preserve_local_state=False,
    ):
        def rows(name):
            return tables.get(name.lower(), [])

        counts = ", ".join(f"{k}={len(v)}" for k, v in sorted(tables.items()) if v)
        self.stdout.write(f"  {counts or '(no rows to import)'}")

        if not rows("tblcompany_locations") and not flush:
            # A live sync legitimately won't touch locations every run once
            # they're all imported — only the initial/dump import needs them
            # present on every call. Only hard-fail when nothing came back
            # at all (e.g. a broken connection returned nothing for anything).
            if not any(tables.values()):
                raise CommandError("No rows were fetched from any table — check the source before trusting an empty run.")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no database changes."))
            return

        with transaction.atomic():
            if flush:
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
            self._import_tag_weights(
                product_by_nid,
                rows("tbljewellery_metal_details"),
                rows("tbljewellery_stone_details"),
                rows("tblstone_sub_category"),
                rows("tblmetalcountry_master"),
                purity_by_nid,
                rows("tblpurity_country_mgmt"),
            )
            item_by_detail_nid, item_by_barcode = self._import_items(
                rows("tblproduct_detail_master"),
                product_by_nid,
                product_location,
                location_by_nid,
                preserve_local_state=preserve_local_state,
            )
            reseller_by_nid = self._import_resellers(rows("tblResellerMaster"))
            reseller_location_by_nid = self._import_reseller_locations(rows("tblresellerlocationMaster"))
            if not skip_assignments:
                master_by_nid = self._import_assignments(
                    rows("tblProductAssignMaster"),
                    rows("tblProductAssign"),
                    rows("tblproduct_barcode_logs"),
                    rows("tblproduct_detail_master"),
                    reseller_by_nid,
                    item_by_detail_nid,
                    item_by_barcode,
                    reseller_location_by_nid,
                    preserve_local_state=preserve_local_state,
                )
            else:
                master_by_nid = {}
            if not skip_payments:
                self._import_reseller_payments(rows("tblAssignPayment_transaction"), master_by_nid)
                self._import_supplier_payments(rows("tblpayment_transaction"), supplier_by_nid, product_by_nid)
            transfer_by_nid = self._import_transfers(
                rows("tblproduct_transfer"),
                rows("tblproduct_transfer_details"),
                location_by_nid,
                item_by_barcode,
            )
            self._import_tracker(
                rows("tblproduct_tracker"),
                rows("tblproduct_tracker_itemsdeatils"),
                location_by_nid,
                item_by_barcode,
                transfer_by_nid,
            )
            self._ensure_login()

    def _flush(self):
        self.stdout.write("Flushing previously imported business data...")
        AuditLogEntry.objects.all().delete()
        TrackerScanItem.objects.all().delete()
        TrackerSession.objects.all().delete()
        ReserveAlert.objects.all().delete()
        ReturnRecord.objects.all().delete()
        ResellerPayment.objects.all().delete()
        SupplierPayment.objects.all().delete()
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
        # ResellerGroup is deliberately NOT flushed — groups are authored
        # in this system, not imported.
        ResellerLocation.objects.all().delete()
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
        if locs:
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
        if types:
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
        return by_nid

    def _import_purities(self, purity_rows, metal_by_nid):
        fallback_metal = next(iter(metal_by_nid.values()), None)
        if fallback_metal is None:
            fallback_metal, _ = Metal.objects.get_or_create(name="Unspecified")
        by_nid = {}
        for row in purity_rows:
            nid = row["nid"]
            name = strip_dflt_prefix(
                as_str(row.get("Metalpurity") or row.get("metalpurity")) or f"Purity {nid}"
            )
            purity, _ = Purity.objects.update_or_create(
                metal=fallback_metal,
                name=name[:50],
            )
            by_nid[nid] = purity
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
        return by_nid

    def _import_products(
        self, products, category_by_nid, subcat_by_nid, currency_by_nid,
        metal_by_nid, purity_by_nid, supplier_by_nid,
    ):
        fallback_cat = category_by_nid.get(None)
        fallback_cur = currency_by_nid.get(None)
        product_by_nid = {}
        product_location = {}
        created_count = 0
        updated_count = 0
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
            obj, created = ProductMaster.objects.update_or_create(
                legacy_id=nid,
                defaults=dict(
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
                    colour=as_str(row.get("colour"))[:50],
                    size=as_str(row.get("size") or row.get("s_size"))[:50],
                    quality=as_str(row.get("quality"))[:50],
                    stone=as_str(row.get("stone"))[:100],
                    metal_rate=as_dec(row.get("metalrate")),
                    convert_rate=as_dec(row.get("Converte_rate")) or Decimal("1"),
                    update_convert_rate=as_dec(row.get("update_convert_rate")),
                    rate_change_status=as_str(row.get("ratechange_status"))[:20],
                    is_active=is_active_flag(row),
                ),
            )
            product_by_nid[nid] = obj
            product_location[nid] = as_int(row.get("company_locationid"))
            if created:
                created_count += 1
            else:
                updated_count += 1
        if products:
            self.stdout.write(self.style.SUCCESS(f"  ProductMaster: {created_count} created, {updated_count} updated"))
        return product_by_nid, product_location

    def _import_tag_weights(
        self, product_by_nid, metal_details, stone_details, stone_subcats,
        metal_countries=None, purity_by_nid=None, purity_countries=None,
    ):
        """Fill tag weight numbers from jewellery metal/stone detail rows.

        Do not copy metal/karat labels from these ids. The same integer is used
        by more than one lookup (country, purity master, purity-country combo),
        and the legacy report pages do not agree. Weight is the raw text on the
        detail row, not a joined name.
        """
        if not product_by_nid:
            return

        diamond_subcat_ids = set()
        for row in stone_subcats or []:
            code = as_str(row.get("code")).upper()
            name = as_str(row.get("name")).lower()
            if code in {"ND", "LGD", "LABGROWN", "DIA", "DIAMOND"} or "diamond" in name:
                # Detail rows reference either nid or sub_cat_id depending on era.
                for key in ("nid", "sub_cat_id"):
                    val = as_str(row.get(key))
                    if val:
                        diamond_subcat_ids.add(val)

        gold_by_pid = {}
        metal_meta_by_pid = {}
        for row in metal_details or []:
            pid = as_int(row.get("product_id"))
            if pid is None:
                continue
            wt = as_str(row.get("weight"))
            if wt and pid not in gold_by_pid:
                gold_by_pid[pid] = wt[:40]
            meta = metal_meta_by_pid.setdefault(pid, {"metal_id": None, "purity_id": None, "weight": None})
            if not meta.get("metal_id"):
                meta["metal_id"] = as_int(row.get("metal_id"))
            if not meta.get("purity_id"):
                meta["purity_id"] = as_int(row.get("metal_purity_id"))
            if meta.get("weight") is None and wt:
                meta["weight"] = as_dec(wt)

        diamond_by_pid = {}
        for row in stone_details or []:
            pid = as_int(row.get("product_id"))
            wt = as_str(row.get("weight"))
            if pid is None or not wt:
                continue
            sub_id = as_str(row.get("stone_subcat_id"))
            if diamond_subcat_ids and sub_id not in diamond_subcat_ids:
                continue
            if not diamond_subcat_ids:
                continue
            diamond_by_pid.setdefault(pid, wt[:40])

        updated = 0
        for pid, product in product_by_nid.items():
            if pid not in gold_by_pid and pid not in diamond_by_pid and pid not in metal_meta_by_pid:
                continue
            gold = gold_by_pid.get(pid, product.gold_weight)
            diamond = diamond_by_pid.get(pid, product.diamond_weight)
            meta = metal_meta_by_pid.get(pid) or {}
            fields = []

            if product.gold_weight != gold or product.diamond_weight != diamond:
                product.gold_weight = gold
                product.diamond_weight = diamond
                fields.extend(["gold_weight", "diamond_weight"])

            net = meta.get("weight")
            if product.net_weight is None and net is not None:
                product.net_weight = net
                fields.append("net_weight")

            if not fields:
                continue
            fields.append("updated_at")
            product.save(update_fields=fields)
            updated += 1
        if metal_details or stone_details:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Tag weights: {len(gold_by_pid)} gold, {len(diamond_by_pid)} diamond "
                    f"({updated} products updated)"
                )
            )

    def _import_items(self, details, product_by_nid, product_location, location_by_nid, *, preserve_local_state=False):
        default_loc = location_by_nid.get(1) or next(iter(location_by_nid.values()), None)
        item_by_detail_nid = {}
        item_by_barcode = {}
        seen_barcodes = set()
        skipped = 0
        created_count = 0
        updated_count = 0
        restated = 0
        moved = 0
        for row in details:
            pmid = as_int(row.get("product_masterid"))
            product = product_by_nid.get(pmid)
            barcode = as_str(row.get("barcode_number"))
            if product is None or not barcode or barcode in seen_barcodes:
                skipped += 1
                continue
            if default_loc is None:
                raise CommandError("No locations available — cannot attach items.")
            seen_barcodes.add(barcode)
            # Same precedence as InventoryLocationHelper.EffectiveLocationSql:
            # per-barcode location first, then the shared product master, then
            # Head Office. Reading only the master (as this did until Sep 2026)
            # collapses every piece of a design onto one location and loses
            # every transfer iadmin has ever recorded.
            loc = (
                location_by_nid.get(as_int(row.get("company_locationid")))
                or location_by_nid.get(product_location.get(pmid))
                or default_loc
            )
            status = map_item_status(row)
            reprint = "PRINTED" if as_str(row.get("barcode_reprint_status")).lower() == "complete" else "NONE"
            nid = row["nid"]
            existing = ProductItem.objects.filter(legacy_id=nid).first()
            if existing is None:
                obj = ProductItem.objects.create(
                    legacy_id=nid,
                    barcode=barcode[:100],
                    product=product,
                    location=loc,
                    status=status,
                    reprint_status=reprint,
                )
                created_count += 1
            else:
                obj = existing
                fields = ["barcode", "product", "updated_at"]
                obj.barcode = barcode[:100]
                obj.product = product
                if not preserve_local_state:
                    if obj.status != status:
                        restated += 1
                    if obj.location_id != loc.pk:
                        moved += 1
                    obj.status = status
                    obj.location = loc
                    obj.reprint_status = reprint
                    fields += ["status", "location", "reprint_status"]
                obj.save(update_fields=fields)
                updated_count += 1
            item_by_detail_nid[nid] = obj
            item_by_barcode[obj.barcode] = obj
        if details:
            self.stdout.write(self.style.SUCCESS(
                f"  ProductItem: {created_count} created, {updated_count} updated, {skipped} skipped (missing product/barcode/duplicate)"
            ))
            if preserve_local_state:
                self.stdout.write("    status/location left as-is (--preserve-local-state)")
            else:
                self.stdout.write(f"    refreshed from iadmin: {restated} status change(s), {moved} location change(s)")
        return item_by_detail_nid, item_by_barcode

    def _import_reseller_locations(self, locations):
        by_nid = {}
        for row in locations:
            nid = row["nid"]
            obj, _ = ResellerLocation.objects.update_or_create(
                legacy_id=nid,
                defaults={
                    "name": (as_str(row.get("locationname")) or f"Location {nid}")[:150],
                    "remarks": as_str(row.get("remarks"))[:200],
                    "is_active": is_active_flag(row),
                },
            )
            by_nid[nid] = obj
            by_nid[str(nid)] = obj
        return by_nid

    def _import_resellers(self, resellers):
        by_nid = {}
        for row in resellers:
            nid = row["nid"]
            name = as_str(row.get("company_name") or row.get("name")) or f"Reseller {nid}"
            obj, _ = Reseller.objects.update_or_create(
                legacy_id=nid,
                defaults={
                    "name": name[:150],
                    "is_active": is_active_flag(row),
                    "address": (as_str(row.get("company_address")) or as_str(row.get("address")))[:255],
                    "contact": (as_str(row.get("cnumber")) or as_str(row.get("contact")))[:100],
                    "email": (as_str(row.get("cemailid")) or as_str(row.get("email")))[:150],
                    "reference_code": str(nid),
                },
            )
            by_nid[nid] = obj
            by_nid[str(nid)] = obj
        return by_nid

    def _import_assignments(
        self, masters, lines, barcode_logs, details,
        reseller_by_nid, item_by_detail_nid, item_by_barcode,
        reseller_location_by_nid=None, preserve_local_state=False,
    ):
        reseller_location_by_nid = reseller_location_by_nid or {}
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
        created_masters = 0
        updated_masters = 0
        for row in masters:
            nid = row["nid"]
            reseller = reseller_by_nid.get(as_int(row.get("reseller_id"))) or reseller_by_nid.get(as_str(row.get("reseller_id")))
            if reseller is None:
                skipped_masters += 1
                continue
            inv = as_str(row.get("invoice_number") or row.get("invoice_name"))
            is_reserve = inv.upper().startswith("RN") or as_str(row.get("invoice_name")).upper().startswith("RN")
            reseller_location = reseller_location_by_nid.get(as_int(row.get("reseller_locationid")))
            existing = AssignmentMaster.all_objects.filter(legacy_id=nid).first()
            if existing is None:
                am = AssignmentMaster(
                    legacy_id=nid,
                    reseller=reseller,
                    reseller_location=reseller_location,
                    is_reserve=is_reserve,
                    invoice_status=map_invoice_status(row),
                    invoice_number=inv[:32],
                )
                am.save()
                created_masters += 1
            else:
                am = existing
                fields = ["reseller", "reseller_location", "is_reserve", "invoice_number", "updated_at"]
                am.reseller = reseller
                am.reseller_location = reseller_location
                am.is_reserve = is_reserve
                if inv:
                    am.invoice_number = inv[:32]
                if not preserve_local_state:
                    # An invoice cancelled in iadmin after first import stayed
                    # COMPLETE here forever without this.
                    am.invoice_status = map_invoice_status(row)
                    fields.append("invoice_status")
                am.save(update_fields=fields)
                updated_masters += 1
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

        # unique_item_per_assignment (master, item) makes this safe to
        # re-run: rows already present from a prior sync are skipped.
        AssignmentLine.objects.bulk_create(line_objs, batch_size=500, ignore_conflicts=True)
        if masters:
            self.stdout.write(self.style.SUCCESS(
                f"  AssignmentMaster: {created_masters} created, {updated_masters} updated "
                f"({skipped_masters} skipped, no reseller)  "
                f"AssignmentLine: {len(line_objs)} candidate rows ({skipped_lines} assign-rows with no barcode)"
            ))
        return master_by_nid

    def _import_reseller_payments(self, payments, master_by_nid):
        created_count = 0
        updated_count = 0
        skipped = 0
        for row in payments:
            master = master_by_nid.get(as_int(row.get("assign_masterid"))) or master_by_nid.get(as_str(row.get("assign_masterid")))
            amount = as_dec(row.get("paid_amount")) or as_dec(row.get("total_amount"))
            nid = row.get("nid")
            if master is None or amount is None or nid is None:
                skipped += 1
                continue
            paid_on = as_date(row.get("credit_date") or row.get("creationdate")) or timezone.now().date()
            note = " ".join(filter(None, [
                as_str(row.get("transaction_number")),
                as_str(row.get("py_number")),
                as_str(row.get("pay_mode")),
            ]))[:255]
            _, created = ResellerPayment.objects.update_or_create(
                legacy_id=nid,
                defaults=dict(assignment=master, amount=amount, paid_on=paid_on, reference_note=note),
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
        if payments:
            self.stdout.write(self.style.SUCCESS(f"  ResellerPayment: {created_count} created, {updated_count} updated ({skipped} skipped)"))

    def _import_supplier_payments(self, payments, supplier_by_nid, product_by_nid):
        created_count = 0
        updated_count = 0
        skipped = 0
        for row in payments:
            supplier = supplier_by_nid.get(as_int(row.get("vender_id"))) or supplier_by_nid.get(as_str(row.get("vender_id")))
            amount = as_dec(row.get("paid_amount")) or as_dec(row.get("total_amount"))
            nid = row.get("nid")
            if supplier is None or amount is None or nid is None:
                skipped += 1
                continue
            product = product_by_nid.get(as_int(row.get("product_id")))
            paid_on = as_date(row.get("credit_date") or row.get("creationdate")) or timezone.now().date()
            note = " ".join(filter(None, [
                as_str(row.get("transaction_number")),
                as_str(row.get("py_number")),
                as_str(row.get("pay_mode")),
            ]))[:255]
            _, created = SupplierPayment.objects.update_or_create(
                legacy_id=nid,
                defaults=dict(supplier=supplier, product=product, amount=amount, paid_on=paid_on, reference_note=note),
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
        if payments:
            self.stdout.write(self.style.SUCCESS(f"  SupplierPayment: {created_count} created, {updated_count} updated ({skipped} skipped)"))

    @staticmethod
    def _flush_lines(model, pending, *, force=False, chunk=2000):
        """bulk_create `pending` once it's worth a round trip, then clear it."""
        if not pending or (not force and len(pending) < chunk):
            return 0
        written = len(pending)
        model.objects.bulk_create(pending, batch_size=500, ignore_conflicts=True)
        pending.clear()
        return written

    def _import_transfers(self, transfers, transfer_details, location_by_nid, item_by_barcode):
        """
        Location-to-location moves already carried out in iadmin.

        Imported as history only — the items were placed at their current
        location by `_import_items` reading the same source, so nothing
        here calls `Transfer.execute()`. Running the moves again would
        fail the from-location check anyway, since the stock has already
        arrived.
        """
        if not transfers:
            return {}

        lines_by_transfer = {}
        for row in transfer_details:
            tid = as_int(row.get("tranfer_id"))
            if tid is not None and is_visible_row(row):
                lines_by_transfer.setdefault(tid, []).append(row)

        transfer_by_nid = {}
        created_count = 0
        updated_count = 0
        skipped = 0
        line_count = 0
        line_objs = []
        for row in transfers:
            nid = row.get("nid")
            from_loc = location_by_nid.get(as_int(row.get("transferid_from")))
            to_loc = location_by_nid.get(as_int(row.get("transferid_to")))
            if nid is None or from_loc is None or to_loc is None or from_loc.pk == to_loc.pk:
                skipped += 1
                continue
            if not is_visible_row(row) or as_str(row.get("active_status"), "active").lower() == "inactive":
                skipped += 1
                continue
            status = map_transfer_status(row)
            obj, created = Transfer.objects.update_or_create(
                legacy_id=nid,
                defaults=dict(from_location=from_loc, to_location=to_loc, status=status),
            )
            moved_on = as_aware(as_date(row.get("transfer_date") or row.get("createiondate")))
            if moved_on:
                Transfer.objects.filter(pk=obj.pk).update(created_at=moved_on)
            transfer_by_nid[nid] = obj
            if created:
                created_count += 1
            else:
                updated_count += 1
            for line in lines_by_transfer.get(nid, []):
                item = item_by_barcode.get(as_str(line.get("pjnumber")))
                if item is not None:
                    line_objs.append(TransferLine(transfer=obj, item=item))
            # A single legacy transfer can carry thousands of barcodes (the
            # 8 Sep 2026 vault-to-showroom move was 2,597 pieces), so don't
            # hold every line of every transfer in memory at once.
            line_count += self._flush_lines(TransferLine, line_objs)

        line_count += self._flush_lines(TransferLine, line_objs, force=True)
        self.stdout.write(self.style.SUCCESS(
            f"  Transfer: {created_count} created, {updated_count} updated ({skipped} skipped), "
            f"{line_count} candidate line(s)"
        ))
        return transfer_by_nid

    def _import_tracker(self, sessions, session_items, location_by_nid, item_by_barcode, transfer_by_nid):
        """
        Stocktake / scan history from `tblproduct_tracker`.

        Without this the dashboard's floor-activity panel reads "no scan
        sessions" on a shop that scans daily, which is a worse lie than
        showing nothing at all — an empty table looks like a quiet day,
        not an unimplemented import.

        Legacy `scan_date` is copied onto `created_at` (which is
        `auto_now_add`, hence the follow-up `.update()`), so "scans today"
        counts the day the scan happened rather than the day it was
        imported.
        """
        if not sessions:
            return

        default_loc = location_by_nid.get(1) or next(iter(location_by_nid.values()), None)
        if default_loc is None:
            return

        items_by_session = {}
        for row in session_items:
            tid = as_int(row.get("trackerid"))
            if tid is not None and is_visible_row(row):
                items_by_session.setdefault(tid, []).append(row)

        incoming_nids = {r["nid"] for r in sessions if r.get("nid") is not None}
        taken_indexes = set(
            TrackerSession.objects.filter(
                Q(legacy_id__isnull=True) | ~Q(legacy_id__in=incoming_nids)
            ).values_list("scan_index", flat=True)
        )
        next_free = max(taken_indexes, default=0)

        session_by_nid = {}
        created_count = 0
        updated_count = 0
        skipped = 0
        scan_line_count = 0
        scan_line_objs = []
        for row in sessions:
            nid = row.get("nid")
            if nid is None or not is_visible_row(row):
                skipped += 1
                continue
            loc = (
                location_by_nid.get(as_int(row.get("from_location_id")))
                or location_by_nid.get(as_int(row.get("to_location_id")))
                or default_loc
            )
            index = as_int(row.get("scan_index")) or nid
            if index in taken_indexes:
                next_free += 1
                index = next_free
            taken_indexes.add(index)
            workflow = as_str(row.get("workflow_mode")).lower()
            transfer = transfer_by_nid.get(as_int(row.get("transfer_id")))
            defaults = dict(
                scan_index=index,
                location=loc,
                mode=map_scan_mode(row),
                item_count=as_int(row.get("items_qty")) or 0,
                is_transfer="transfer" in workflow or transfer is not None,
                transfer=transfer,
            )
            obj, created = TrackerSession.objects.update_or_create(legacy_id=nid, defaults=defaults)
            scanned_at = as_aware(row.get("operated_at") or row.get("scan_date") or row.get("creationdate"))
            if scanned_at:
                TrackerSession.objects.filter(pk=obj.pk).update(created_at=scanned_at)
            session_by_nid[nid] = obj
            if created:
                created_count += 1
            else:
                updated_count += 1

            for line in items_by_session.get(nid, []):
                item = item_by_barcode.get(as_str(line.get("pjnumber")))
                if item is None:
                    continue
                scan_line_objs.append(TrackerScanItem(
                    session=obj,
                    item=item,
                    result=SCAN_RESULT_BY_LEGACY_LOCATION.get(
                        as_str(line.get("pjnumber_location")).lower(), ""
                    ),
                    location_at_scan=loc,
                    is_extra=as_str(line.get("item_action")).lower() == "extra",
                ))
            scan_line_count += self._flush_lines(TrackerScanItem, scan_line_objs)

        scan_line_count += self._flush_lines(TrackerScanItem, scan_line_objs, force=True)

        # Second pass: a closing scan's parent may appear later in the file.
        linked = 0
        for row in sessions:
            child = session_by_nid.get(row.get("nid"))
            parent_ids = split_id_list(row.get("parent_tracker_ids"))
            if child is None or not parent_ids:
                continue
            parent = session_by_nid.get(parent_ids[0])
            if parent is not None and child.parent_session_id != parent.pk:
                child.parent_session = parent
                child.save(update_fields=["parent_session", "updated_at"])
                linked += 1

        self.stdout.write(self.style.SUCCESS(
            f"  TrackerSession: {created_count} created, {updated_count} updated ({skipped} skipped), "
            f"{scan_line_count} candidate scan line(s), {linked} closing scan(s) linked"
        ))

    def _ensure_login(self):
        from django.core.management import call_command
        call_command("ensure_local_admin")
