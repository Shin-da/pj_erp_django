"""
Generate missing ProductImage.thumbnail files from the full camera originals.

Use after a CLI import that stored only ``image`` (e.g. import_product_images
before thumbs existed), or after turning PRODUCT_PHOTO_THUMB_WIDTH back on.

    python manage.py backfill_product_image_thumbs
    python manage.py backfill_product_image_thumbs --limit 50 --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.catalogue.models import ProductImage
from apps.catalogue.photos import ensure_thumbnail


class Command(BaseCommand):
    help = "Create missing list/gallery thumbnails for ProductImage rows."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rebuild even when a thumbnail already exists.",
        )

    def handle(self, *args, **opts):
        qs = ProductImage.objects.select_related("product").order_by("id")
        if not opts["force"]:
            qs = qs.filter(thumbnail="")
        if opts["limit"]:
            qs = qs[: opts["limit"]]

        total = qs.count() if not opts["limit"] else min(opts["limit"], ProductImage.objects.count())
        self.stdout.write(f"Candidates: {total}  dry_run={opts['dry_run']} force={opts['force']}")

        made = skipped = failed = 0
        for img in qs.iterator():
            if img.thumbnail and not opts["force"]:
                skipped += 1
                continue
            if opts["dry_run"]:
                made += 1
                continue
            if opts["force"] and img.thumbnail:
                img.thumbnail.delete(save=False)
                img.thumbnail = ""
                img.save(update_fields=["thumbnail", "updated_at"])
            if ensure_thumbnail(img):
                made += 1
                if made % 50 == 0:
                    self.stdout.write(f"  … {made}")
            else:
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. thumbs={made} skipped={skipped} failed={failed} dry_run={opts['dry_run']}"
            )
        )
