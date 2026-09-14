"""
Link image objects already in Spaces/R2 to ProductImage rows by PJ in the filename.

Does not re-upload — sets FileField.name to the existing object key.

    python manage.py link_spaces_photos_by_filename
    python manage.py link_spaces_photos_by_filename --prefix product_images/2026/09/ --dry-run
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalogue.models import ProductImage
from apps.catalogue.photos import (
    CODE_RE,
    IMG_EXT,
    _kind_for_name,
    _photo_limits,
    _thumb_bytes,
    resolve_product_by_code,
)
from django.core.files.base import ContentFile


class Command(BaseCommand):
    help = "Create ProductImage rows for existing object-storage keys named with PJ codes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prefix",
            default="product_images/",
            help="Only consider keys under this prefix (default: product_images/).",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument(
            "--make-thumbs",
            action="store_true",
            help="Download each original once and write a thumbnail (slower).",
        )
        parser.add_argument(
            "--stage-unmatched",
            action="store_true",
            help="Also stage unknown PJ codes as floating photos (requires photo staging models).",
        )

    def handle(self, *args, **opts):
        if not settings.USE_S3_MEDIA:
            raise CommandError("AWS_STORAGE_BUCKET_NAME is not set.")

        prefix = (opts["prefix"] or "").lstrip("/")
        dry_run = opts["dry_run"]
        make_thumbs = opts["make_thumbs"]
        client = default_storage.connection.meta.client
        bucket = default_storage.bucket_name

        keys: list[str] = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents") or []:
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                ext = Path(key).suffix.lower()
                if ext not in IMG_EXT and ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                    continue
                keys.append(key)

        keys.sort()
        if opts["limit"]:
            keys = keys[: opts["limit"]]

        self.stdout.write(
            f"Bucket={bucket} prefix={prefix!r} candidates={len(keys)} "
            f"dry_run={dry_run} make_thumbs={make_thumbs}"
        )

        attached = skipped = unmatched = failed = 0
        unmatched_rows: list[tuple[str, str]] = []
        _, _, _, thumb_w, thumb_q = _photo_limits()

        for i, key in enumerate(keys, 1):
            fname = Path(key).name
            codes = [m.group(1).upper() for m in CODE_RE.finditer(fname)]
            # dedupe preserve order
            seen, codes_u = set(), []
            for c in codes:
                if c not in seen:
                    seen.add(c)
                    codes_u.append(c)
            codes = codes_u

            if not codes:
                unmatched += 1
                unmatched_rows.append((key, "no PJ code in filename"))
                continue

            products = []
            missing = []
            for code in codes:
                p = resolve_product_by_code(code)
                if p:
                    products.append(p)
                else:
                    missing.append(code)
            if not products:
                unmatched += 1
                unmatched_rows.append((key, f"codes not found: {', '.join(missing)}"))
                continue

            thumb_data = None
            if make_thumbs and not dry_run:
                try:
                    obj = client.get_object(Bucket=bucket, Key=key)
                    raw = obj["Body"].read()
                    thumb_data = _thumb_bytes(raw, width=thumb_w, quality=thumb_q)
                except Exception as exc:
                    self.stdout.write(self.style.WARNING(f"thumb fail {key}: {exc}"))

            for product in products:
                if ProductImage.objects.filter(product=product, source_filename=fname).exists():
                    skipped += 1
                    continue
                # also skip if same storage key already linked
                if ProductImage.objects.filter(product=product, image=key).exists():
                    skipped += 1
                    continue

                if dry_run:
                    attached += 1
                    continue

                try:
                    with transaction.atomic():
                        make_primary = not ProductImage.objects.filter(
                            product=product, is_primary=True
                        ).exists()
                        img = ProductImage(
                            product=product,
                            kind=_kind_for_name(fname),
                            is_primary=make_primary,
                            source_filename=fname,
                            caption=Path(fname).stem[:200],
                        )
                        img.image.name = key
                        if thumb_data:
                            stem = codes[0]
                            img.thumbnail.save(
                                f"{stem}_t.jpg", ContentFile(thumb_data), save=False
                            )
                        img.save()
                    attached += 1
                except Exception as exc:
                    failed += 1
                    unmatched_rows.append((key, f"save failed: {exc}"))

            if i % 100 == 0:
                self.stdout.write(f"  … {i}/{len(keys)}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"  keys scanned : {len(keys)}"))
        self.stdout.write(self.style.SUCCESS(f"  attached     : {attached}" + (" (dry run)" if dry_run else "")))
        self.stdout.write(self.style.WARNING(f"  skipped      : {skipped}"))
        self.stdout.write(self.style.WARNING(f"  unmatched    : {unmatched}"))
        if failed:
            self.stdout.write(self.style.ERROR(f"  failed       : {failed}"))
        for key, why in unmatched_rows[:20]:
            self.stdout.write(f"      - {key}  ({why})")
        if len(unmatched_rows) > 20:
            self.stdout.write(f"      … and {len(unmatched_rows) - 20} more")
