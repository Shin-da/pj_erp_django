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

CODE_RE = re.compile(r"(?:(?<![A-Za-z])[A-Z]-)?(?<![A-Za-z])(PJ\d{4,7})(?!\d)", re.IGNORECASE)  # (?!\d) not \b: filenames are often "PJ22171_xxx.jpg" and "_" is a word char so \b never fires after the digits
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".tif", ".tiff"}
CERT_HINT = re.compile(r"cert", re.IGNORECASE)

# Catalogue storage: 0 = keep the uploaded bytes (full camera resolution).
# Set PRODUCT_PHOTO_MAX_WIDTH > 0 only if you want web-sized JPEGs instead.
DEFAULT_RESIZE_PX = 0
DEFAULT_JPEG_QUALITY = 88
DEFAULT_THUMB_WIDTH = 480
DEFAULT_THUMB_QUALITY = 78
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


def _photo_limits() -> tuple[int, int, int, int, int]:
    """(max_width_px, jpeg_quality, max_upload_bytes, thumb_width, thumb_quality)."""
    try:
        from django.conf import settings

        resize = int(getattr(settings, "PRODUCT_PHOTO_MAX_WIDTH", DEFAULT_RESIZE_PX))
        quality = int(getattr(settings, "PRODUCT_PHOTO_JPEG_QUALITY", DEFAULT_JPEG_QUALITY))
        max_bytes = int(getattr(settings, "PRODUCT_PHOTO_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES))
        thumb_w = int(getattr(settings, "PRODUCT_PHOTO_THUMB_WIDTH", DEFAULT_THUMB_WIDTH))
        thumb_q = int(getattr(settings, "PRODUCT_PHOTO_THUMB_QUALITY", DEFAULT_THUMB_QUALITY))
    except Exception:  # pragma: no cover — settings not configured
        resize = DEFAULT_RESIZE_PX
        quality = DEFAULT_JPEG_QUALITY
        max_bytes = DEFAULT_MAX_UPLOAD_BYTES
        thumb_w = DEFAULT_THUMB_WIDTH
        thumb_q = DEFAULT_THUMB_QUALITY
    return (
        max(0, resize),
        max(1, min(quality, 95)),
        max(1, max_bytes),
        max(0, thumb_w),
        max(1, min(thumb_q, 95)),
    )


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


def _thumb_bytes(raw: bytes, width: int = DEFAULT_THUMB_WIDTH, quality: int = DEFAULT_THUMB_QUALITY) -> bytes | None:
    """Build a small JPEG for list/gallery display. Returns None if Pillow cannot decode."""
    if not width or not HAVE_PIL:
        return None
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    except Exception:
        return None
    if im.width > width:
        im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def _save_thumbnail(
    img,
    raw: bytes,
    *,
    thumb_width: int,
    thumb_quality: int,
    stem: str | None = None,
) -> None:
    data = _thumb_bytes(raw, width=thumb_width, quality=thumb_quality)
    if not data:
        return
    if not stem:
        product = getattr(img, "product", None)
        if product is not None:
            stem = normalize_code(product.reference_id) or f"p{product.pk}"
        else:
            stem = normalize_code(getattr(img, "hinted_code", "") or "") or f"s{getattr(img, 'pk', 0) or '0'}"
    img.thumbnail.save(f"{stem}_t.jpg", ContentFile(data), save=False)


def ensure_thumbnail(image: ProductImage) -> bool:
    """Create a missing thumb from the full file. Returns True if a thumb exists afterward."""
    if image.thumbnail:
        return True
    if not image.image:
        return False
    _, _, _, thumb_w, thumb_q = _photo_limits()
    if not thumb_w or not HAVE_PIL:
        return False
    try:
        image.image.open("rb")
        raw = image.image.read()
    except Exception:
        return False
    finally:
        try:
            image.image.close()
        except Exception:
            pass
    data = _thumb_bytes(raw, width=thumb_w, quality=thumb_q)
    if not data:
        return False
    stem = normalize_code(image.product.reference_id) or f"p{image.product_id}"
    image.thumbnail.save(f"{stem}_t.jpg", ContentFile(data), save=True)
    return True


def image_public_dict(image: ProductImage, request=None) -> dict:
    """JSON-friendly image payload for HTML AJAX and the write API."""

    def _abs(url: str) -> str:
        if request and url:
            return request.build_absolute_uri(url)
        return url

    full = image.image.url if image.image else ""
    thumb = image.thumbnail.url if image.thumbnail else full
    return {
        "id": image.pk,
        "url": _abs(full),
        "thumb_url": _abs(thumb),
        "kind": image.kind,
        "is_primary": image.is_primary,
        "caption": image.caption,
        "source_filename": image.source_filename,
        "order": image.order,
    }


def set_primary_image(image: ProductImage) -> ProductImage:
    """Make ``image`` the sole primary for its design."""
    with transaction.atomic():
        ProductImage.objects.filter(product_id=image.product_id, is_primary=True).exclude(
            pk=image.pk
        ).update(is_primary=False)
        if not image.is_primary:
            image.is_primary = True
            image.save(update_fields=["is_primary", "updated_at"])
    return image


def delete_product_image(image: ProductImage) -> None:
    """Remove the DB row and files in local/S3/Spaces storage. Promote a new primary if needed."""
    product = image.product
    was_primary = image.is_primary
    if image.thumbnail:
        image.thumbnail.delete(save=False)
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


def _create_image(
    product: ProductMaster,
    *,
    raw: bytes,
    filename: str,
    caption: str,
    resize: int,
    quality: int,
    thumb_width: int,
    thumb_quality: int,
    stem: str,
    has_primary_cache: dict[int, bool] | None = None,
) -> ProductImage | None:
    """Persist one ProductImage (+ thumb). Returns None when skipped as duplicate."""
    if ProductImage.objects.filter(product=product, source_filename=filename).exists():
        return None

    data, ext = _resize_bytes(raw, filename, resize=resize, quality=quality)
    with transaction.atomic():
        if has_primary_cache is not None:
            if product.pk not in has_primary_cache:
                has_primary_cache[product.pk] = ProductImage.objects.filter(
                    product=product, is_primary=True
                ).exists()
            make_primary = not has_primary_cache[product.pk]
        else:
            make_primary = not ProductImage.objects.filter(
                product=product, is_primary=True
            ).exists()
        img = ProductImage(
            product=product,
            kind=_kind_for_name(filename),
            is_primary=make_primary,
            source_filename=filename,
            caption=(caption or "")[:200],
        )
        img.image.save(f"{stem}.{ext}", ContentFile(data), save=False)
        # Prefer original camera bytes for the thumb so quality isn't double-compressed
        # when the stored file was already resized.
        _save_thumbnail(img, raw if resize == 0 else data, thumb_width=thumb_width, thumb_quality=thumb_quality)
        img.save()
        if has_primary_cache is not None and make_primary:
            has_primary_cache[product.pk] = True
    return img


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
    d_resize, d_quality, d_max, d_thumb_w, d_thumb_q = _photo_limits()
    if resize is None:
        resize = d_resize
    if quality is None:
        quality = d_quality
    if max_bytes is None:
        max_bytes = d_max

    created = 0
    skipped = 0
    errors: list[str] = []
    images: list[ProductImage] = []

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

        stem = normalize_code(product.reference_id) or f"p{product.pk}"
        img = _create_image(
            product,
            raw=raw,
            filename=name,
            caption=caption or name,
            resize=resize,
            quality=quality,
            thumb_width=d_thumb_w,
            thumb_quality=d_thumb_q,
            stem=stem,
        )
        if img is None:
            skipped += 1
            continue
        images.append(img)
        created += 1

    return {
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "images": images,
    }


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
    d_resize, d_quality, d_max, d_thumb_w, d_thumb_q = _photo_limits()
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
    images: list[ProductImage] = []
    cache: dict[str, ProductMaster | None] = {}
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
        for product in products:
            if ProductImage.objects.filter(product=product, source_filename=name).exists():
                skipped += 1
                products_touched.add(product.pk)
                continue
            img = _create_image(
                product,
                raw=raw,
                filename=name,
                caption=name,
                resize=resize,
                quality=quality,
                thumb_width=d_thumb_w,
                thumb_quality=d_thumb_q,
                stem=codes[0],
                has_primary_cache=has_primary,
            )
            if img is None:
                skipped += 1
                products_touched.add(product.pk)
                continue
            images.append(img)
            images_created += 1
            products_touched.add(product.pk)

    return {
        "matched_files": matched_files,
        "created": images_created,
        "skipped": skipped,
        "unmatched": unmatched,
        "products_touched": len(products_touched),
        "images": images,
    }
