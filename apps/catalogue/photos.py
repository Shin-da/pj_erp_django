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


def _resize_bytes(raw: bytes, filename: str, resize: int = 1600, quality: int = 72) -> tuple[bytes, str]:
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


def attach_uploaded_images(
    product: ProductMaster,
    uploads: Iterable[UploadedFile],
    *,
    caption: str = "",
    resize: int = 1600,
    quality: int = 72,
) -> dict:
    """
    Save one or more uploaded files as ProductImage rows on ``product``.

    Skips a (product, source_filename) pair already stored. First photo
    on a design with no primary becomes primary.
    """
    created = 0
    skipped = 0
    errors: list[str] = []

    for upload in uploads:
        name = (getattr(upload, "name", None) or "upload.jpg").strip()
        if not name:
            errors.append("Empty filename skipped.")
            continue
        raw = upload.read()
        if not raw:
            errors.append(f"{name}: empty file.")
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
    resize: int = 1600,
    quality: int = 72,
) -> dict:
    """
    Match each file's PJ token(s) in the filename to designs and attach.

    Same rules as ``import_product_images``. Files with no code, or codes
    that do not resolve, are reported as unmatched.
    """
    matched_files = 0
    images_created = 0
    skipped = 0
    unmatched: list[tuple[str, str]] = []
    products_touched: set[int] = set()
    cache: dict[str, ProductMaster | None] = {}

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

        matched_files += 1
        raw = upload.read()
        if not raw:
            unmatched.append((name, "empty file"))
            continue
        data, ext = _resize_bytes(raw, name, resize=resize, quality=quality)

        for product in products:
            if ProductImage.objects.filter(product=product, source_filename=name).exists():
                skipped += 1
                products_touched.add(product.pk)
                continue
            with transaction.atomic():
                make_primary = not ProductImage.objects.filter(
                    product=product, is_primary=True
                ).exists()
                img = ProductImage(
                    product=product,
                    kind=_kind_for_name(name),
                    is_primary=make_primary,
                    source_filename=name,
                    caption=name[:200],
                )
                img.image.save(f"{codes[0]}.{ext}", ContentFile(data), save=False)
                img.save()
            images_created += 1
            products_touched.add(product.pk)

    return {
        "matched_files": matched_files,
        "created": images_created,
        "skipped": skipped,
        "unmatched": unmatched,
        "products_touched": len(products_touched),
    }
