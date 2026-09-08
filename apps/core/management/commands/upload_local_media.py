"""
Push files from local MEDIA_ROOT into the configured default storage.

Use after switching production to S3/R2 so existing ``product_images/``,
``reseller_logos/``, and ``legacy/`` keys keep working without rewriting
DB rows — FileField stores the relative key, not a host-specific URL.

Usage (activated venv, project root, with AWS_* / bucket env set):

    python manage.py upload_local_media
    python manage.py upload_local_media --dry-run
    python manage.py upload_local_media --prefix product_images/
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Upload local MEDIA_ROOT files into the active default storage (S3/R2)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be uploaded; write nothing.",
        )
        parser.add_argument(
            "--prefix",
            default="",
            help="Only upload keys under this relative prefix (e.g. product_images/).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-upload even when the remote key already exists.",
        )

    def handle(self, *args, **options):
        if not settings.USE_S3_MEDIA:
            raise CommandError(
                "AWS_STORAGE_BUCKET_NAME is not set — default storage is still "
                "local FileSystemStorage. Configure S3/R2 env vars first."
            )

        root = Path(settings.MEDIA_ROOT)
        if not root.is_dir():
            raise CommandError(f"MEDIA_ROOT does not exist: {root}")

        prefix = (options["prefix"] or "").replace("\\", "/").lstrip("/")
        dry_run = options["dry_run"]
        force = options["force"]

        # PutObject with the exact key — django-storages save() can append
        # a random suffix when file_overwrite=False, which would break DB paths.
        client = default_storage.connection.meta.client
        bucket = default_storage.bucket_name

        uploaded = skipped = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            key = path.relative_to(root).as_posix()
            if prefix and not key.startswith(prefix):
                continue

            exists = default_storage.exists(key)
            if exists and not force:
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"would upload {key}" + (" (replace)" if exists else "")
                )
                uploaded += 1
                continue

            extra = {}
            params = getattr(default_storage, "object_parameters", None) or {}
            if params:
                extra.update(params)
            content_type = _guess_content_type(path)
            if content_type:
                extra["ContentType"] = content_type

            with path.open("rb") as fh:
                if extra:
                    client.upload_fileobj(fh, bucket, key, ExtraArgs=extra)
                else:
                    client.upload_fileobj(fh, bucket, key)
            self.stdout.write(self.style.SUCCESS(f"uploaded {key}"))
            uploaded += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. uploaded={uploaded} skipped_existing={skipped} "
                f"dry_run={dry_run} force={force}"
            )
        )


def _guess_content_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".pdf": "application/pdf",
    }.get(ext, "")
