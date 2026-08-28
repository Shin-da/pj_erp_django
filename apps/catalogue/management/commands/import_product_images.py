"""
Attach a folder of jewellery photographs to the products they depict.

The photo files are named with the PJ item code(s) they show, e.g.

    PJ22899 73,013 18K WG D1.35ct 7g.JPG
    B-PJ22188 172,904 18K PG ... N-PJ22148 308,732 ...JPG   (two items, one shot)
    DSC00002(1).JPG                                          (no code -> unmatched)

For each file this pulls out every ``PJ<digits>`` token, matches it to a
product (``inventory.ProductItem.barcode`` first — that column literally
holds ``PJ21115`` etc. in this database — then ``catalogue.ProductMaster.
reference_id`` as a fallback), resizes the image, and stores it as a
``catalogue.ProductImage`` row under ``MEDIA_ROOT/product_images/``.

The originals are only ever read. Re-running is safe: a (product,
source_filename) pair already stored is skipped.

Usage (activated venv, project root):

    python manage.py import_product_images "C:/Users/ONEGAI_SERVER/Downloads/PERFECT JEWELRY IMAGES"

Options:
    --dry-run        Report what would happen; touch nothing.
    --resize N       Max width in px for the stored copy (default 1600).
                     0 keeps the original bytes (no Pillow needed).
    --quality Q      JPEG quality for resized copies (default 72).
    --limit N        Stop after N source files (for a quick trial).
    --report PATH    Where to write the unmatched-files CSV
                     (default: <folder>/_unmatched.csv).
    --primary-only-if-none
                     Default behaviour: a file becomes a product's primary
                     image only when that product has none yet. Pass this
                     flag off with --no-... is not needed; it is already
                     the only mode. (Kept documented so the rule is clear.)
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalogue.models import ProductImage, ProductMaster
from apps.inventory.models import ProductItem

try:
    from PIL import Image, ImageOps

    HAVE_PIL = True
except ImportError:  # pragma: no cover - environment dependent
    HAVE_PIL = False

# PJ codes: 4–6 digits, optional single-letter category prefix we discard
# (B-/N-/E-/P-/R- = Bracelet/Necklace/Earring/Pendant/Ring).
CODE_RE = re.compile(r"(?:\b[A-Z]-)?\b(PJ\d{4,6})\b", re.IGNORECASE)
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
CERT_HINT = re.compile(r"cert", re.IGNORECASE)


class Command(BaseCommand):
    help = "Import jewellery photos from a folder, matching files to products by PJ code in the filename."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Folder to scan (searched recursively).")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--resize", type=int, default=1600,
                            help="Max width px for stored copy; 0 = keep original bytes.")
        parser.add_argument("--quality", type=int, default=72)
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--report", default="")

    # -- helpers ---------------------------------------------------------

    def _codes(self, filename: str) -> list[str]:
        seen, out = set(), []
        for m in CODE_RE.finditer(filename):
            code = m.group(1).upper()
            if code not in seen:
                seen.add(code)
                out.append(code)
        return out

    def _resolve(self, code: str, cache: dict) -> ProductMaster | None:
        if code in cache:
            return cache[code]
        item = (
            ProductItem.objects.filter(barcode__iexact=code)
            .select_related("product")
            .first()
        )
        product = item.product if item else (
            ProductMaster.objects.filter(reference_id__iexact=code).first()
        )
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

    # -- main ----------------------------------------------------------------

    def handle(self, *args, **opts):
        root = Path(opts["path"]).expanduser()
        if not root.is_dir():
            raise CommandError(f"Not a folder: {root}")

        resize = max(0, opts["resize"])
        if resize and not HAVE_PIL:
            self.stdout.write(self.style.WARNING(
                "Pillow not installed — storing originals unmodified. "
                "`pip install Pillow` (or add it to requirements.txt) to resize."
            ))
            resize = 0

        files = sorted(
            p for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in IMG_EXT and not p.name.startswith("_")
        )
        if opts["limit"]:
            files = files[: opts["limit"]]

        report_path = Path(opts["report"]) if opts["report"] else root / "_unmatched.csv"
        cache: dict[str, ProductMaster | None] = {}

        n_files = len(files)
        matched_files = 0
        images_created = 0
        skipped_existing = 0
        products_touched: set[int] = set()
        unmatched: list[tuple[str, str]] = []

        self.stdout.write(
            f"Scanning {n_files} image file(s) under {root}"
            + (f"  (resize max {resize}px q{opts['quality']})" if resize else "  (originals, no resize)")
            + ("  [DRY RUN]" if opts["dry_run"] else "")
        )

        for i, src in enumerate(files, 1):
            codes = self._codes(src.name)
            if not codes:
                unmatched.append((src.name, "no PJ code in filename"))
                continue

            products = []
            missing = []
            for code in codes:
                p = self._resolve(code, cache)
                (products if p else missing).append(p if p else code)

            if not products:
                unmatched.append((src.name, f"codes not found: {', '.join(missing)}"))
                continue

            matched_files += 1
            kind = ProductImage.Kind.CERTIFICATE if CERT_HINT.search(src.name) else ProductImage.Kind.PHOTO
            data = ext = None  # lazily built once per file, reused across multi-product links

            for product in products:
                if ProductImage.objects.filter(product=product, source_filename=src.name).exists():
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
                        source_filename=src.name,
                        caption=Path(src.name).stem[:200],
                    )
                    stem = codes[0]
                    img.image.save(f"{stem}.{ext}", ContentFile(data), save=False)
                    img.save()
                images_created += 1
                products_touched.add(product.pk)

            if i % 100 == 0:
                self.stdout.write(f"  … {i}/{n_files}")

        # unmatched report
        if unmatched and not opts["dry_run"]:
            with open(report_path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["filename", "reason"])
                w.writerows(unmatched)

        s = self.style
        self.stdout.write("")
        self.stdout.write(s.SUCCESS(f"  files scanned      : {n_files}"))
        self.stdout.write(s.SUCCESS(f"  files matched      : {matched_files}"))
        self.stdout.write(s.SUCCESS(f"  images created     : {images_created}"
                                    + (" (dry run)" if opts['dry_run'] else "")))
        self.stdout.write(s.SUCCESS(f"  products with photos: {len(products_touched)}"))
        if skipped_existing:
            self.stdout.write(s.WARNING(f"  skipped (already imported): {skipped_existing}"))
        self.stdout.write(s.WARNING(f"  unmatched files    : {len(unmatched)}"))
        if unmatched and not opts["dry_run"]:
            self.stdout.write(f"  unmatched list     : {report_path}")
        if opts["dry_run"] and unmatched:
            for name, why in unmatched[:15]:
                self.stdout.write(f"      - {name}  ({why})")
            if len(unmatched) > 15:
                self.stdout.write(f"      … and {len(unmatched) - 15} more")
