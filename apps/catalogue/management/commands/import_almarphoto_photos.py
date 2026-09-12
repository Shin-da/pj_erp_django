"""
One-time migration: attach photos from the standalone `almarphoto` PHP/MySQL
app (C:/xampp/htdocs/almarphoto) to the products they depict here.

almarphoto keeps one `items` row per (set of) PJ code(s), with a `photos`
JSON column of paths relative to its own folder, e.g.
``uploads/1789034294_0_PJ17510.JPG``. This command reads a JSON export of
that table (see `_legacy_import_scratch/almarphoto_items.json`, produced by
querying `db.php`'s connection directly — there is no MySQL driver in this
project's own requirements, so the export step is external to this command),
matches each row's PJ code(s) to a product exactly like
`import_product_images` does (`inventory.ProductItem.barcode` first, then
`catalogue.ProductMaster.reference_id`), and copies+resizes each photo into
a `catalogue.ProductImage`.

Confirmed against a live legacy sync (2026-09-11): roughly 28% of almarphoto
rows have a PJ code with no matching product here at all, spread evenly
across almarphoto's whole history — not a sync lag, an ongoing gap between
"photographed" and "tagged in iadmin". By default those rows are still just
reported and left untouched. Pass --create-unverified to instead create a
minimal `ProductMaster(is_verified=False)` for each one, so the photo has
somewhere to live — Category defaults to Jewellery (JWL), currency/supplier
resolved or created from almarphoto's own fields, everything else guessed
from almarphoto data that was never confirmed against real tagged stock.
These rows are meant to be reconciled: a future `sync_legacy_mssql` run that
finds a real product for the same reference_id should be pointed at merging
into this row (not implemented yet — see catalogue.ProductMaster.is_verified
docstring) rather than creating a duplicate.

Usage (activated venv, project root):

    python manage.py import_almarphoto_photos _legacy_import_scratch/almarphoto_items.json
    python manage.py import_almarphoto_photos _legacy_import_scratch/almarphoto_items.json --create-unverified

Options:
    --source PATH    Folder the `photos` paths are relative to
                     (default: C:/xampp/htdocs/almarphoto).
    --create-unverified
                     Create a provisional, is_verified=False ProductMaster for
                     a row whose code matches nothing, instead of skipping it.
    --default-category CODE
                     Category code used for a provisional product (default: JWL).
    --dry-run        Report what would happen; touch nothing.
    --resize N       Max width in px for the stored copy (default 1600).
                     0 keeps the original bytes (no Pillow needed).
    --quality Q      JPEG quality for resized copies (default 72).
    --limit N        Stop after N almarphoto rows (for a quick trial).
    --report PATH    Where to write the still-unmatched-rows CSV
                     (default: <export file's folder>/_almarphoto_unmatched.csv).
"""

from __future__ import annotations

import csv
import io
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalogue.models import Category, Currency, ProductImage, ProductMaster, Supplier
from apps.inventory.models import ProductItem

try:
    from PIL import Image, ImageOps

    HAVE_PIL = True
except ImportError:  # pragma: no cover - environment dependent
    HAVE_PIL = False

DEFAULT_SOURCE = "C:/xampp/htdocs/almarphoto"
CODE_RE = re.compile(r"(PJ\d{4,7})", re.IGNORECASE)


class Command(BaseCommand):
    help = "Attach photos from the almarphoto app's exported `items` JSON to matching products."

    def add_arguments(self, parser):
        parser.add_argument("export_json", help="Path to the almarphoto items JSON export.")
        parser.add_argument("--source", default=DEFAULT_SOURCE,
                            help="Folder the export's `photos` paths are relative to.")
        parser.add_argument("--create-unverified", action="store_true",
                            help="Create a provisional ProductMaster for an unmatched code instead of skipping it.")
        parser.add_argument("--default-category", default="JWL",
                            help="Category code for a provisional product (default: JWL).")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--resize", type=int, default=1600,
                            help="Max width px for stored copy; 0 = keep original bytes.")
        parser.add_argument("--quality", type=int, default=72)
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--report", default="")

    # -- helpers ---------------------------------------------------------

    def _codes(self, item_code: str) -> list[str]:
        seen, out = set(), []
        for m in CODE_RE.finditer(item_code.upper()):
            code = m.group(1)
            if code not in seen:
                seen.add(code)
                out.append(code)
        return out

    def _find_existing(self, code: str) -> ProductMaster | None:
        item = (
            ProductItem.objects.filter(barcode__iexact=code)
            .select_related("product")
            .first()
        )
        return item.product if item else (
            ProductMaster.objects.filter(reference_id__iexact=code).first()
        )

    def _currency_for(self, code: str, ctx: dict) -> Currency:
        code = (code or "").strip().upper() or "PHP"
        cache = ctx["currency_cache"]
        if code not in cache:
            cache[code] = Currency.objects.filter(code__iexact=code).first() or cache.get("PHP")
        return cache[code]

    def _supplier_for(self, name: str, ctx: dict) -> Supplier | None:
        name = (name or "").strip()
        if not name:
            return None
        cache = ctx["supplier_cache"]
        if name not in cache:
            cache[name], _ = Supplier.objects.get_or_create(name=name[:150])
        return cache[name]

    def _make_provisional(self, code: str, row: dict, ctx: dict) -> ProductMaster:
        item_type = (row.get("item_type") or "").strip()
        description = (row.get("item_description") or "").strip()
        name = description or item_type or code

        price_raw = str(row.get("price") or "0").replace(",", "").strip()
        try:
            price = Decimal(price_raw) if price_raw else None
        except InvalidOperation:
            price = None

        product = ProductMaster.objects.create(
            reference_id=code,
            name=name[:200],
            category=ctx["category"],
            subcategory=item_type[:100],
            currency=self._currency_for(row.get("currency"), ctx),
            supplier=self._supplier_for(row.get("supplier"), ctx),
            colour=(row.get("color") or "")[:50],
            selling_price=price,
            is_verified=False,
        )
        return product

    def _resolve(self, code: str, row: dict, ctx: dict) -> ProductMaster | None:
        cache = ctx["cache"]
        if code in cache:
            return cache[code]
        product = self._find_existing(code)
        if product is None and ctx["create_unverified"]:
            if ctx["dry_run"]:
                # Unsaved stand-in: counts as "would resolve" without touching the DB.
                product = ProductMaster(reference_id=code, is_verified=False)
            else:
                product = self._make_provisional(code, row, ctx)
            ctx["provisional_created"] += 1
        cache[code] = product
        return product

    def _bytes(self, src: Path, resize: int, quality: int) -> tuple[bytes, str]:
        raw = src.read_bytes()
        if not resize or not HAVE_PIL:
            return raw, src.suffix.lower().lstrip(".") or "jpg"
        try:
            im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
        except Exception:  # unreadable / not really an image — store as-is
            return raw, src.suffix.lower().lstrip(".") or "jpg"
        if im.width > resize:
            im = im.resize((resize, round(im.height * resize / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
        return buf.getvalue(), "jpg"

    # -- main --------------------------------------------------------------

    def handle(self, *args, **opts):
        export_path = Path(opts["export_json"]).expanduser()
        if not export_path.is_file():
            raise CommandError(f"Not a file: {export_path}")

        source_root = Path(opts["source"]).expanduser()
        if not source_root.is_dir():
            raise CommandError(f"Source folder not found: {source_root}")

        resize = max(0, opts["resize"])
        if resize and not HAVE_PIL:
            self.stdout.write(self.style.WARNING(
                "Pillow not installed — storing originals unmodified."
            ))
            resize = 0

        ctx = {
            "cache": {},
            "currency_cache": {"PHP": Currency.objects.filter(code__iexact="PHP").first()},
            "supplier_cache": {},
            "create_unverified": opts["create_unverified"],
            "dry_run": opts["dry_run"],
            "provisional_created": 0,
        }
        if opts["create_unverified"]:
            category = Category.objects.filter(code__iexact=opts["default_category"]).first()
            if category is None:
                raise CommandError(
                    f"--create-unverified needs Category code={opts['default_category']!r} to exist."
                )
            ctx["category"] = category
            if ctx["currency_cache"]["PHP"] is None:
                raise CommandError("--create-unverified needs Currency code='PHP' to exist.")

        rows = json.loads(export_path.read_text(encoding="utf-8"))
        if opts["limit"]:
            rows = rows[: opts["limit"]]

        report_path = Path(opts["report"]) if opts["report"] else export_path.parent / "_almarphoto_unmatched.csv"

        n_rows = len(rows)
        matched_rows = 0
        images_created = 0
        skipped_existing = 0
        missing_files = 0
        products_touched: set[int] = set()
        unmatched: list[tuple[str, str]] = []

        self.stdout.write(
            f"Processing {n_rows} almarphoto row(s) from {export_path}"
            + (f"  (resize max {resize}px q{opts['quality']})" if resize else "  (originals, no resize)")
            + ("  [create-unverified]" if opts["create_unverified"] else "")
            + ("  [DRY RUN]" if opts["dry_run"] else "")
        )

        for i, row in enumerate(rows, 1):
            raw_code = (row.get("item_code") or "").strip()
            codes = self._codes(raw_code)
            photos = row.get("photos") or []

            if not codes:
                unmatched.append((raw_code or f"(row id {row.get('id')})", "no PJ code in item_code"))
                continue

            products = []
            missing = []
            for code in codes:
                p = self._resolve(code, row, ctx)
                (products if p else missing).append(p if p else code)

            if not products:
                unmatched.append((raw_code, f"codes not found: {', '.join(missing)}"))
                continue

            matched_rows += 1

            for rel_path in photos:
                src = source_root / rel_path
                if not src.is_file():
                    missing_files += 1
                    continue

                fname = src.name
                kind = ProductImage.Kind.PHOTO
                data = ext = None

                for product in products:
                    if product is None or product.pk is None:
                        # dry-run provisional: nothing to attach to yet
                        continue
                    if ProductImage.objects.filter(product=product, source_filename=fname).exists():
                        skipped_existing += 1
                        products_touched.add(product.pk)
                        continue

                    if opts["dry_run"]:
                        images_created += 1
                        products_touched.add(product.pk)
                        continue

                    if data is None:
                        data, ext = self._bytes(src, resize, opts["quality"])

                    with transaction.atomic():
                        make_primary = not ProductImage.objects.filter(
                            product=product, is_primary=True
                        ).exists()
                        img = ProductImage(
                            product=product,
                            kind=kind,
                            is_primary=make_primary,
                            source_filename=fname,
                            caption=raw_code[:200],
                        )
                        img.image.save(f"{codes[0]}.{ext}", ContentFile(data), save=False)
                        img.save()
                    images_created += 1
                    products_touched.add(product.pk)

            if i % 100 == 0:
                self.stdout.write(f"  … {i}/{n_rows}")

        if unmatched and not opts["dry_run"]:
            with open(report_path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["item_code", "reason"])
                w.writerows(unmatched)

        s = self.style
        self.stdout.write("")
        self.stdout.write(s.SUCCESS(f"  rows processed        : {n_rows}"))
        self.stdout.write(s.SUCCESS(f"  rows matched          : {matched_rows}"))
        if opts["create_unverified"]:
            self.stdout.write(s.SUCCESS(f"  provisional products  : {ctx['provisional_created']}"
                                        + (" (dry run)" if opts['dry_run'] else "")))
        self.stdout.write(s.SUCCESS(f"  images created        : {images_created}"
                                    + (" (dry run)" if opts['dry_run'] else "")))
        self.stdout.write(s.SUCCESS(f"  products with photos  : {len(products_touched)}"))
        if skipped_existing:
            self.stdout.write(s.WARNING(f"  skipped (already imported): {skipped_existing}"))
        if missing_files:
            self.stdout.write(s.WARNING(f"  photo files not found on disk: {missing_files}"))
        self.stdout.write(s.WARNING(f"  still unmatched rows  : {len(unmatched)}"))
        if unmatched and not opts["dry_run"]:
            self.stdout.write(f"  unmatched list        : {report_path}")
        if opts["dry_run"] and unmatched:
            for name, why in unmatched[:15]:
                self.stdout.write(f"      - {name}  ({why})")
            if len(unmatched) > 15:
                self.stdout.write(f"      … and {len(unmatched) - 15} more")
