"""
Attach jewellery photographs to designs by PJ / barcode.

Stock intake (`/products/add/`) creates ProductMaster + ProductItem rows.
Photo people use a separate flow (`/products/photos/`) but the same
login/permission system, and the same link chain:

    barcode (ProductItem) → design (ProductMaster) → ProductImage

Resolution matches the import commands: barcode first, then
reference_id. Photos hang off the design — pieces that share a design
share its gallery.
"""

from __future__ import annotations

import io
import re
from typing import Iterable

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from apps.catalogue.models import ProductImage, ProductMaster
from apps.inventory.models import ProductItem

try:
    from PIL import Image, ImageOps

    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

CODE_RE = re.compile(r"(?:\b[A-Z]-)?\b(PJ\d{4,6})\b", re.IGNORECASE)
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".tif", ".tiff"}
CERT_HINT = re.compile(r"cert", re.IGNORECASE)

# Catalogue storage: 0 = keep the uploaded bytes (full camera resolution).
# Set PRODUCT_PHOTO_MAX_WIDTH > 0 only if you want web-sized JPEGs instead.
DEFAULT_RESIZE_PX = 0
DEFAULT_JPEG_QUALITY = 88
# Per-file cap for high-res camera JPEGs / PNG / WebP. Spaces/R2 can hold
# more; this only guards the app host from a runaway upload.
DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


def normalize_code(raw: str) -> str:
    return (raw or "").strip().upper()


def codes_in_filename(filename: str) -> list[str]:
    seen, out = set(), []
    for m in CODE_RE.finditer(filename or ""):
        code = m.group(1).upper()
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def resolve_product_by_code(code: str) -> ProductMaster | None:
    """
    Map a scanned / typed PJ code to its design.

    Prefer the physical piece barcode (that column holds PJ21115 etc.),
    then fall back to ProductMaster.reference_id for designs that exist
    without a piece yet (e.g. provisional almarphoto rows).
    """
    code = normalize_code(code)
    if not code:
        return None
    item = (
        ProductItem.objects.filter(barcode__iexact=code)
        .select_related("product")
        .first()
    )
    if item:
        return item.product
    return ProductMaster.objects.filter(reference_id__iexact=code).first()


def _kind_for_name(filename: str) -> str:
    if CERT_HINT.search(filename or ""):
        return ProductImage.Kind.CERTIFICATE
    return ProductImage.Kind.PHOTO


def _photo_limits() -> tuple[int, int, int]:
    """(max_width_px, jpeg_quality, max_upload_bytes) from Django settings when available."""
    try:
        from django.conf import settings

        resize = int(getattr(settings, "PRODUCT_PHOTO_MAX_WIDTH", DEFAULT_RESIZE_PX))
        quality = int(getattr(settings, "PRODUCT_PHOTO_JPEG_QUALITY", DEFAULT_JPEG_QUALITY))
        max_bytes = int(getattr(settings, "PRODUCT_PHOTO_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES))
    except Exception:  # pragma: no cover — settings not configured
        resize, quality, max_bytes = DEFAULT_RESIZE_PX, DEFAULT_JPEG_QUALITY, DEFAULT_MAX_UPLOAD_BYTES
    return max(0, resize), max(1, min(quality, 95)), max(1, max_bytes)


def _read_upload(upload: UploadedFile, max_bytes: int) -> tuple[bytes | None, str | None]:
    """
    Read an uploaded file with a hard size cap.

    Large camera JPEGs stream to a temp file once they exceed
    FILE_UPLOAD_MAX_MEMORY_SIZE; we still enforce max_bytes so a bulk
    drop cannot exhaust disk/RAM on the app host.
    """
    size = getattr(upload, "size", None)
    if size is not None and size > max_bytes:
        mb = max_bytes / (1024 * 1024)
        return None, f"larger than {mb:.0f} MB limit"
    raw = upload.read()
    if not raw:
        return None, "empty file"
    if len(raw) > max_bytes:
        mb = max_bytes / (1024 * 1024)
        return None, f"larger than {mb:.0f} MB limit"
    return raw, None


def _resize_bytes(raw: bytes, filename: str, resize: int = DEFAULT_RESIZE_PX, quality: int = DEFAULT_JPEG_QUALITY) -> tuple[bytes, str]:
    """
    Optionally downscale for catalogue storage.

    resize=0 (default) keeps the original bytes and extension — use this for
    high-quality camera files on Spaces / R2. When resize > 0, convert to a
    progressive JPEG at that max width.
    """
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "jpg").lower()
    if not resize or not HAVE_PIL:
        return raw, ext or "jpg"
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    except Exception:
        return raw, ext or "jpg"
    if im.width > resize:
        im = im.resize((resize, round(im.height * resize / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue(), "jpg"


def delete_product_image(image: ProductImage) -> None:
    """Remove the DB row and the file in local/S3/Spaces storage. Promote a new primary if needed."""
    product = image.product
    was_primary = image.is_primary
    if image.image:
        image.image.delete(save=False)
    image.delete()
    if was_primary:
        nxt = product.images.order_by("order", "id").first()
        if nxt and not nxt.is_primary:
            nxt.is_primary = True
            nxt.save(update_fields=["is_primary", "updated_at"])


def delete_all_product_images(product: ProductMaster) -> int:
    """Delete every photo on a design. Returns how many rows were removed."""
    n = 0
    for img in list(product.images.all()):
        delete_product_image(img)
        n += 1
    return n


def attach_uploaded_images(
    product: ProductMaster,
    uploads: Iterable[UploadedFile],
    *,
    caption: str = "",
    resize: int | None = None,
    quality: int | None = None,
    max_bytes: int | None = None,
) -> dict:
    """
    Save one or more uploaded files as ProductImage rows on ``product``.

    Skips a (product, source_filename) pair already stored. First photo
    on a design with no primary becomes primary. By default the original
    camera file is stored as-is (see PRODUCT_PHOTO_MAX_WIDTH).
    """
    if resize is None or quality is None or max_bytes is None:
        d_resize, d_quality, d_max = _photo_limits()
        if resize is None:
            resize = d_resize
        if quality is None:
            quality = d_quality
        if max_bytes is None:
            max_bytes = d_max

    created = 0
    skipped = 0
    errors: list[str] = []

    for upload in uploads:
        name = (getattr(upload, "name", None) or "upload.jpg").strip()
        if not name:
            errors.append("Empty filename skipped.")
            continue
        raw, err = _read_upload(upload, max_bytes)
        if err:
            errors.append(f"{name}: {err}.")
            continue

        if ProductImage.objects.filter(product=product, source_filename=name).exists():
            skipped += 1
            continue

        data, ext = _resize_bytes(raw, name, resize=resize, quality=quality)
        with transaction.atomic():
            make_primary = not ProductImage.objects.filter(
                product=product, is_primary=True
            ).exists()
            img = ProductImage(
                product=product,
                kind=_kind_for_name(name),
                is_primary=make_primary,
                source_filename=name,
                caption=(caption or "")[:200],
            )
            safe_stem = normalize_code(product.reference_id) or f"p{product.pk}"
            img.image.save(f"{safe_stem}.{ext}", ContentFile(data), save=False)
            img.save()
        created += 1

    return {"created": created, "skipped": skipped, "errors": errors}


def attach_bulk_by_filename(
    uploads: Iterable[UploadedFile],
    *,
    resize: int | None = None,
    quality: int | None = None,
    max_bytes: int | None = None,
) -> dict:
    """
    Match each file's PJ token(s) in the filename to designs and attach.

    Same rules as ``import_product_images``. Files with no code, or codes
    that do not resolve, are reported as unmatched. Oversized / empty
    files land in unmatched with a reason (not silently dropped).
    """
    if resize is None or quality is None or max_bytes is None:
        d_resize, d_quality, d_max = _photo_limits()
        if resize is None:
            resize = d_resize
        if quality is None:
            quality = d_quality
        if max_bytes is None:
            max_bytes = d_max

    matched_files = 0
    images_created = 0
    skipped = 0
    unmatched: list[tuple[str, str]] = []
    products_touched: set[int] = set()
    cache: dict[str, ProductMaster | None] = {}
    # Avoid N+1 primary checks inside a large bulk drop.
    has_primary: dict[int, bool] = {}

    for upload in uploads:
        name = (getattr(upload, "name", None) or "").strip()
        if not name:
            unmatched.append(("(empty)", "no filename"))
            continue
        codes = codes_in_filename(name)
        if not codes:
            unmatched.append((name, "no PJ code in filename"))
            continue

        products: list[ProductMaster] = []
        missing: list[str] = []
        for code in codes:
            if code not in cache:
                cache[code] = resolve_product_by_code(code)
            p = cache[code]
            if p:
                products.append(p)
            else:
                missing.append(code)

        if not products:
            unmatched.append((name, f"codes not found: {', '.join(missing)}"))
            continue

        raw, err = _read_upload(upload, max_bytes)
        if err:
            unmatched.append((name, err))
            continue

        matched_files += 1
        data, ext = _resize_bytes(raw, name, resize=resize, quality=quality)

        for product in products:
            if ProductImage.objects.filter(product=product, source_filename=name).exists():
                skipped += 1
                products_touched.add(product.pk)
                continue
            with transaction.atomic():
                if product.pk not in has_primary:
                    has_primary[product.pk] = ProductImage.objects.filter(
                        product=product, is_primary=True
                    ).exists()
                make_primary = not has_primary[product.pk]
                img = ProductImage(
                    product=product,
                    kind=_kind_for_name(name),
                    is_primary=make_primary,
                    source_filename=name,
                    caption=name[:200],
                )
                img.image.save(f"{codes[0]}.{ext}", ContentFile(data), save=False)
                img.save()
                if make_primary:
                    has_primary[product.pk] = True
            images_created += 1
            products_touched.add(product.pk)

    return {
        "matched_files": matched_files,
        "created": images_created,
        "skipped": skipped,
        "unmatched": unmatched,
        "products_touched": len(products_touched),
    }
