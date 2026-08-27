"""
Import the legacy stock_rfid_backup.sql dump (tblcompany_locations,
tbljewellery_type, tblproduct_master, tblproduct_detail_master) into the
Django models: locations.Location, catalogue.Category/Currency/Supplier/
ProductMaster, inventory.ProductItem.

This is a first-pass, local/test-env import. Per explicit direction from
Shin (24 Aug 2026): insert directly, discrepancies are OK for now since
this is a local dev database, not production. Several legacy lookup
tables referenced by numeric codes were NOT present in the dump we have
(vendor/supplier names, metal names, currency names, and the true
sub_category lookup table are all opaque numeric codes here) — those are
handled with clearly-labelled placeholder values rather than blocking the
import. See the mapping notes below and the "Known gaps" section printed
at the end of the run.

Usage (from the activated venv, in the pj-erp project root):

    python manage.py import_legacy_stock_rfid

Options:
    --dir PATH     Directory containing the *_inserts.sql extracts.
                   Defaults to <BASE_DIR>/_legacy_import_scratch
    --flush        Delete all previously-imported data first (Location,
                   Category, Currency, Supplier, ProductMaster,
                   ProductItem) so re-running this command doesn't create
                   duplicate rows. Recommended on every run except the
                   very first, since ProductMaster has no natural unique
                   key we can safely upsert on (legacy reference_id has
                   82 collisions in the real data).
    --dry-run      Parse and report counts only; no database writes.

Mapping decisions (all pragmatic / local-only, per Shin's go-ahead):
  - Location: 4 legacy rows (HO/Admin Room/Show Room/Pullout Items) map
    1:1 by legacy nid -> location_type (HEAD_OFFICE/OTHER/SHOWROOM/PULLOUT).
  - Category: tblproduct_master.sub_category is a numeric code (20 distinct
    values, e.g. 4, 6, 7, 8, 9...) that does NOT match the 6-row
    tbljewellery_type table (codes go up to 40). The real lookup table
    for sub_category was not found in this dump. Each distinct
    sub_category code becomes its own placeholder Category
    ("Legacy sub-category 7", code "SC7") so products stay groupable;
    this should be replaced with real category names once/if the actual
    lookup table is located.
  - Currency: tblproduct_master.CurrencyType is also a numeric code (95,
    87, 88, 94) with no lookup table in this dump. All products are
    assigned a single placeholder Currency ("PHP") rather than guessing
    at 4 unknown currencies.
  - Supplier: tblproduct_master.vendor_id is numeric with no vendor-name
    table in this dump. Each distinct vendor_id becomes a placeholder
    Supplier ("Vendor 16", reference_code "16").
  - Metal / Purity: tblproduct_master.metal and .metal_purity_id are
    almost entirely NULL/0 (6163/6656 null) and the populated values are
    opaque numeric codes with no lookup table in this dump. Left NULL on
    every ProductMaster rather than inventing metal names.
  - company_locationid (design-level location, used as the item's
    location since tblproduct_detail_master has no location column in
    this dump): NULL -> Location nid=1 (HO) default; 4528 rows already
    point at nid=1, 10 at nid=4 (Pullout), 2118 are NULL -> defaulted to HO.
  - Status: tblproduct_detail_master has four separate status columns.
    item_current_status is treated as authoritative: 'sold' -> SOLD,
    'reserve' -> RESERVED, else assign_status=='complete' -> ASSIGNED,
    else PENDING.
  - reprint_status: barcode_reprint_status 'complete' -> PRINTED, else NONE.
"""

import re
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.locations.models import Location, LocationType
from apps.catalogue.models import Category, Currency, Supplier, ProductMaster
from apps.inventory.models import ProductItem, StockStatus


INSERT_RE = re.compile(r"^INSERT \[dbo\]\.\[(\w+)\] \((.*?)\) VALUES \((.*)\)\s*$")


def split_columns(col_str):
    return [c.strip().strip("[]") for c in col_str.split(",")]


def split_top_level(s):
    """Split a VALUES(...) inner string on top-level commas, respecting
    N'...'-quoted strings (with '' as an escaped quote) and nested parens
    (for CAST(...) expressions)."""
    parts = []
    depth = 0
    in_str = False
    buf = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if in_str:
            if ch == "'":
                if i + 1 < n and s[i + 1] == "'":
                    buf.append("''")
                    i += 2
                    continue
                in_str = False
                buf.append(ch)
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue
        if ch == "'":
            in_str = True
            buf.append(ch)
            i += 1
            continue
        if ch == "(":
            depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch == ")":
            depth -= 1
            buf.append(ch)
            i += 1
            continue
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return parts


def parse_literal(tok):
    tok = tok.strip()
    if tok == "NULL":
        return None
    m = re.match(r"^CAST\((.*)\s+AS\s+[\w()0-9, ]+\)$", tok, re.IGNORECASE | re.DOTALL)
    if m:
        return parse_literal(m.group(1).strip())
    if tok.startswith("N'") and tok.endswith("'"):
        return tok[2:-1].replace("''", "'")
    if tok.startswith("'") and tok.endswith("'"):
        return tok[1:-1].replace("''", "'")
    try:
        if re.match(r"^-?\d+$", tok):
            return int(tok)
        return float(tok)
    except ValueError:
        return tok


def parse_file(path, stdout):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.startswith("INSERT"):
                continue
            m = INSERT_RE.match(line)
            if not m:
                stdout.write(f"  [skip, no match] {line[:150]}")
                continue
            columns = split_columns(m.group(2))
            raw_values = split_top_level(m.group(3))
            if len(raw_values) != len(columns):
                stdout.write(f"  [skip, column count mismatch] {line[:150]}")
                continue
            values = [parse_literal(v) for v in raw_values]
            rows.append(dict(zip(columns, values)))
    return rows


LOCATION_TYPE_BY_NID = {
    1: LocationType.HEAD_OFFICE,   # HO
    2: LocationType.OTHER,         # Admin Room
    3: LocationType.SHOWROOM,      # Show Room
    4: LocationType.PULLOUT,       # Pullout Items
}


def dec(val):
    """Legacy numeric columns are nvarchar; coerce blank/None/garbage to None."""
    if val is None:
        return None
    s = str(val).strip()
    if s == "":
        return None
    try:
        return s
    except (TypeError, ValueError):
        return None


class Command(BaseCommand):
    help = "Import the legacy stock_rfid_backup.sql extract into Location/Category/Currency/Supplier/ProductMaster/ProductItem."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dir",
            default=str(Path(settings.BASE_DIR) / "_legacy_import_scratch"),
            help="Directory containing loc_inserts.sql / product_inserts.sql / detail_inserts.sql",
        )
        parser.add_argument("--flush", action="store_true", help="Delete previously-imported rows first")
        parser.add_argument("--dry-run", action="store_true", help="Parse and report only, no DB writes")

    def handle(self, *args, **opts):
        src = Path(opts["dir"])
        loc_file = src / "loc_inserts.sql"
        product_file = src / "product_inserts.sql"
        detail_file = src / "detail_inserts.sql"

        for f in (loc_file, product_file, detail_file):
            if not f.exists():
                self.stderr.write(self.style.ERROR(f"Missing expected file: {f}"))
                sys.exit(1)

        self.stdout.write("Parsing legacy SQL extracts...")
        locs = parse_file(loc_file, self.stdout)
        products = parse_file(product_file, self.stdout)
        details = parse_file(detail_file, self.stdout)
        self.stdout.write(f"  locations: {len(locs)}  products: {len(products)}  detail/items: {len(details)}")

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — no database changes made."))
            return

        with transaction.atomic():
            if opts["flush"]:
                self.stdout.write("Flushing previously-imported data...")
                ProductItem.objects.all().delete()
                ProductMaster.objects.all().delete()
                Supplier.objects.all().delete()
                Category.objects.all().delete()
                Currency.objects.filter(code="PHP").delete()
                Location.objects.all().delete()

            # --- Locations -----------------------------------------------------
            location_by_nid = {}
            for row in locs:
                nid = row["nid"]
                loc, _ = Location.objects.update_or_create(
                    code=row["location_code"],
                    defaults={
                        "name": row["location_name"],
                        "location_type": LOCATION_TYPE_BY_NID.get(nid, LocationType.OTHER),
                        "is_active": row.get("active_status") == "active",
                    },
                )
                location_by_nid[nid] = loc
            default_location = location_by_nid.get(1)
            self.stdout.write(self.style.SUCCESS(f"  Locations: {len(location_by_nid)} imported"))

            # --- Categories (placeholder, keyed on sub_category code) ----------
            category_by_subcat = {}
            distinct_subcats = sorted({row.get("sub_category") for row in products if row.get("sub_category") not in (None, "")}, key=str)
            for code in distinct_subcats:
                cat, _ = Category.objects.update_or_create(
                    code=f"SC{code}"[:10],
                    defaults={"name": f"Legacy sub-category {code}"},
                )
                category_by_subcat[code] = cat
            fallback_category, _ = Category.objects.update_or_create(
                code="SCUNK", defaults={"name": "Legacy sub-category (unknown)"}
            )
            self.stdout.write(self.style.SUCCESS(f"  Categories: {len(category_by_subcat)} placeholder categories"))

            # --- Currency (single placeholder) ----------------------------------
            currency, _ = Currency.objects.update_or_create(code="PHP", defaults={"symbol": "₱"})

            # --- Suppliers (placeholder, keyed on vendor_id) --------------------
            supplier_by_vendor = {}
            distinct_vendors = sorted({row.get("vendor_id") for row in products if row.get("vendor_id") not in (None, "")}, key=str)
            for vid in distinct_vendors:
                sup, _ = Supplier.objects.update_or_create(
                    reference_code=str(vid),
                    defaults={"name": f"Vendor {vid}"},
                )
                supplier_by_vendor[vid] = sup
            self.stdout.write(self.style.SUCCESS(f"  Suppliers: {len(supplier_by_vendor)} placeholder suppliers"))

            # --- ProductMaster ---------------------------------------------------
            product_by_nid = {}
            created_products = 0
            for row in products:
                cat = category_by_subcat.get(row.get("sub_category"), fallback_category)
                sup = supplier_by_vendor.get(row.get("vendor_id"))
                pm = ProductMaster.objects.create(
                    reference_id=row.get("reference_id") or "",
                    name=row.get("product_Name") or f"Legacy item {row['nid']}",
                    category=cat,
                    currency=currency,
                    metal=None,
                    purity=None,
                    supplier=sup,
                    net_weight=dec(row.get("net_wt")),
                    gross_weight=dec(row.get("gross_wt")),
                    purchase_price=dec(row.get("purchase_price")) or dec(row.get("actual_price")),
                    selling_price=dec(row.get("selling_price")),
                    is_active=row.get("active_status") == "active",
                )
                product_by_nid[row["nid"]] = (pm, row.get("company_locationid"))
                created_products += 1
            self.stdout.write(self.style.SUCCESS(f"  ProductMaster: {created_products} created"))

            # --- ProductItem -------------------------------------------------------
            created_items = 0
            skipped_items = 0
            for row in details:
                pmid_raw = row.get("product_masterid")
                try:
                    pmid = int(pmid_raw) if pmid_raw is not None else None
                except (TypeError, ValueError):
                    pmid = None
                entry = product_by_nid.get(pmid)
                if entry is None:
                    skipped_items += 1
                    continue
                pm, company_locationid = entry
                loc = location_by_nid.get(company_locationid, default_location)

                ics = row.get("item_current_status")
                if ics == "sold":
                    status = StockStatus.SOLD
                elif ics == "reserve":
                    status = StockStatus.RESERVED
                elif row.get("assign_status") == "complete":
                    status = StockStatus.ASSIGNED
                else:
                    status = StockStatus.PENDING

                reprint = "PRINTED" if row.get("barcode_reprint_status") == "complete" else "NONE"

                barcode = row.get("barcode_number")
                if not barcode:
                    skipped_items += 1
                    continue

                ProductItem.objects.update_or_create(
                    barcode=barcode,
                    defaults={
                        "product": pm,
                        "location": loc,
                        "status": status,
                        "reprint_status": reprint,
                    },
                )
                created_items += 1
            self.stdout.write(self.style.SUCCESS(f"  ProductItem: {created_items} created/updated, {skipped_items} skipped (no matching product/barcode)"))

        self.stdout.write(self.style.SUCCESS("Import complete."))
        self.stdout.write(self.style.WARNING(
            "Known gaps (placeholder data, needs real lookup tables to fix later):\n"
            "  - Category is keyed on the opaque sub_category code, not a real category name.\n"
            "  - Currency is a single placeholder 'PHP' for every product (CurrencyType codes were not resolved).\n"
            "  - Supplier names are placeholders ('Vendor <id>') — no vendor-name table was in this dump.\n"
            "  - Metal/Purity were left blank on every product (opaque codes, mostly NULL anyway).\n"
        ))
