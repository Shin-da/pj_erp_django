"""
Floating photo staging + upload history.

Photo staff can upload before stock people create the PJ. Files land as
``StagedProductImage`` rows (status WAITING). When a matching barcode /
reference_id appears, ``claim_staged_for_code`` attaches them to the design.
Every file also stays on its ``PhotoUploadBatch`` for full history.
"""

from __future__ import annotations

from typing import Iterable

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.catalogue.models import (
    PhotoUploadBatch,
    ProductImage,
    ProductMaster,
    StagedProductImage,
)
from apps.catalogue.photos import (
    _create_image,
    _kind_for_name,
    _photo_limits,
    _read_upload,
    _resize_bytes,
    _save_thumbnail,
    codes_in_filename,
    normalize_code,
    resolve_product_by_code,
)


def client_meta(request) -> dict:
    if request is None:
        return {"ip_address": None, "user_agent": ""}
    ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    if not ip:
        ip = request.META.get("REMOTE_ADDR") or None
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:400]
    return {"ip_address": ip or None, "user_agent": ua}


def start_batch(
    *,
    user=None,
    mode: str = PhotoUploadBatch.Mode.SINGLE,
    source: str = "",
    note: str = "",
    target_code: str = "",
    request=None,
) -> PhotoUploadBatch:
    meta = client_meta(request)
    return PhotoUploadBatch.objects.create(
        uploaded_by=user if getattr(user, "is_authenticated", False) else None,
        mode=mode,
        source=(source or "")[:80],
        note=(note or "")[:255],
        target_code=normalize_code(target_code),
        ip_address=meta["ip_address"],
        user_agent=meta["user_agent"],
    )


def _store_staged_file(
    staged: StagedProductImage,
    raw: bytes,
    filename: str,
    *,
    resize: int,
    quality: int,
    thumb_w: int,
    thumb_q: int,
) -> None:
    data, ext = _resize_bytes(raw, filename, resize=resize, quality=quality)
    stem = (staged.hinted_code or "staged").replace("/", "_")[:40] or "staged"
    staged.image.save(f"{stem}.{ext}", ContentFile(data), save=False)
    _save_thumbnail(
        staged,
        raw if resize == 0 else data,
        thumb_width=thumb_w,
        thumb_quality=thumb_q,
    )


def _attach_staged_to_product(
    staged: StagedProductImage,
    product: ProductMaster,
    *,
    user=None,
    raw: bytes | None = None,
) -> ProductImage | None:
    """Copy staged bytes onto a ProductImage and mark the staged row ATTACHED."""
    if ProductImage.objects.filter(
        product=product, source_filename=staged.source_filename
    ).exists():
        staged.status = StagedProductImage.Status.SKIPPED
        staged.status_detail = "already on design"
        staged.product = product
        staged.save(
            update_fields=["status", "status_detail", "product", "updated_at"]
        )
        return None

    resize, quality, _max_b, thumb_w, thumb_q = _photo_limits()
    if raw is None:
        staged.image.open("rb")
        try:
            raw = staged.image.read()
        finally:
            staged.image.close()

    img = _create_image(
        product,
        raw=raw,
        filename=staged.source_filename,
        caption=staged.hinted_code or staged.source_filename,
        resize=resize,
        quality=quality,
        thumb_width=thumb_w,
        thumb_quality=thumb_q,
        stem=normalize_code(product.reference_id)
        or staged.hinted_code
        or f"p{product.pk}",
    )
    if img is None:
        staged.status = StagedProductImage.Status.SKIPPED
        staged.status_detail = "already on design"
        staged.product = product
        staged.save(
            update_fields=["status", "status_detail", "product", "updated_at"]
        )
        return None

    staged.status = StagedProductImage.Status.ATTACHED
    staged.status_detail = ""
    staged.product = product
    staged.product_image = img
    staged.attached_at = timezone.now()
    staged.attached_by = user if getattr(user, "is_authenticated", False) else None
    staged.save(
        update_fields=[
            "status",
            "status_detail",
            "product",
            "product_image",
            "attached_at",
            "attached_by",
            "updated_at",
        ]
    )
    return img


def process_uploads(
    uploads: Iterable[UploadedFile],
    *,
    batch: PhotoUploadBatch,
    user=None,
    force_code: str = "",
    stage_unmatched: bool = True,
    allow_no_code: bool = True,
) -> dict:
    """
    Handle one or more uploaded files for a batch.

    - If ``force_code`` resolves to a product → attach.
    - Else if filename PJ token(s) resolve → attach to each match.
    - Else if ``stage_unmatched`` → keep as WAITING (floating).
    - Else → FAILED with reason.
    """
    resize, quality, max_bytes, thumb_w, thumb_q = _photo_limits()
    force_code = normalize_code(force_code)
    forced_product = resolve_product_by_code(force_code) if force_code else None

    attached = 0
    staged = 0
    skipped = 0
    failed = 0
    images: list[ProductImage] = []
    waiting: list[StagedProductImage] = []
    unmatched: list[tuple[str, str]] = []

    for upload in uploads:
        name = (getattr(upload, "name", None) or "upload.jpg").strip() or "upload.jpg"
        content_type = getattr(upload, "content_type", "") or ""
        size = int(getattr(upload, "size", 0) or 0)
        codes = codes_in_filename(name)
        hinted = force_code or (codes[0] if codes else "")

        raw, err = _read_upload(upload, max_bytes)
        row = StagedProductImage(
            batch=batch,
            source_filename=name,
            original_name=name,
            file_size=size or (len(raw) if raw else 0),
            content_type=content_type[:100],
            kind=_kind_for_name(name),
            extracted_codes=codes,
            hinted_code=hinted,
        )

        if err or raw is None:
            row.status = StagedProductImage.Status.FAILED
            row.status_detail = err or "empty file"
            # still need a placeholder file? skip file storage
            row.image = ""  # will fail NOT NULL - need empty content file
            row.image.save("failed.bin", ContentFile(b""), save=False)
            row.save()
            failed += 1
            unmatched.append((name, row.status_detail))
            continue

        _store_staged_file(
            row, raw, name, resize=resize, quality=quality, thumb_w=thumb_w, thumb_q=thumb_q
        )

        products: list[ProductMaster] = []
        if forced_product is not None:
            products = [forced_product]
        elif force_code and not codes:
            # Typed a future PJ with no filename token — float under that code.
            row.status = StagedProductImage.Status.WAITING
            row.hinted_code = force_code
            row.status_detail = f"waiting for PJ: {force_code}"
            row.save()
            staged += 1
            waiting.append(row)
            unmatched.append((name, row.status_detail))
            continue
        else:
            missing = []
            for code in codes:
                p = resolve_product_by_code(code)
                if p:
                    products.append(p)
                else:
                    missing.append(code)
            if codes and not products:
                # all codes unknown → stage waiting for those codes
                row.status = StagedProductImage.Status.WAITING
                row.status_detail = f"waiting for PJ: {', '.join(missing)}"
                row.save()
                if stage_unmatched:
                    staged += 1
                    waiting.append(row)
                    unmatched.append((name, row.status_detail))
                else:
                    row.status = StagedProductImage.Status.FAILED
                    row.status_detail = f"codes not found: {', '.join(missing)}"
                    row.save(update_fields=["status", "status_detail", "updated_at"])
                    failed += 1
                    unmatched.append((name, row.status_detail))
                continue
            if not codes:
                if allow_no_code and stage_unmatched:
                    row.status = StagedProductImage.Status.WAITING
                    row.status_detail = "no PJ code in filename — assign manually"
                    row.save()
                    staged += 1
                    waiting.append(row)
                    unmatched.append((name, row.status_detail))
                    continue
                row.status = StagedProductImage.Status.FAILED
                row.status_detail = "no PJ code in filename"
                row.save()
                failed += 1
                unmatched.append((name, row.status_detail))
                continue

        # Attach to resolved products (one staged row → first product; extras get ProductImage only)
        row.save()  # persist file first
        first = True
        any_attached = False
        for product in products:
            if first:
                img = _attach_staged_to_product(row, product, user=user, raw=raw)
                first = False
                if img:
                    images.append(img)
                    attached += 1
                    any_attached = True
                elif row.status == StagedProductImage.Status.SKIPPED:
                    skipped += 1
            else:
                # additional designs sharing the shot
                img = _create_image(
                    product,
                    raw=raw,
                    filename=name,
                    caption=name,
                    resize=resize,
                    quality=quality,
                    thumb_width=thumb_w,
                    thumb_quality=thumb_q,
                    stem=codes[0] if codes else f"p{product.pk}",
                )
                if img:
                    images.append(img)
                    attached += 1
                    any_attached = True
                else:
                    skipped += 1

        if not any_attached and row.status == StagedProductImage.Status.WAITING:
            staged += 1
            waiting.append(row)

    batch.refresh_counts()
    return {
        "batch_id": batch.pk,
        "attached": attached,
        "created": attached,  # alias for older UI/API
        "staged": staged,
        "skipped": skipped,
        "failed": failed,
        "images": images,
        "waiting": waiting,
        "unmatched": unmatched,
        "matched_files": attached + skipped,
        "products_touched": len({im.product_id for im in images}),
    }


def claim_staged_for_code(code: str, product: ProductMaster | None = None, *, user=None) -> dict:
    """
    Attach every WAITING staged photo whose hinted/extracted code matches.

    Called when stock intake creates a barcode / reference_id.
    """
    code = normalize_code(code)
    if not code:
        return {"claimed": 0, "skipped": 0}
    product = product or resolve_product_by_code(code)
    if product is None:
        return {"claimed": 0, "skipped": 0}

    qs = (
        StagedProductImage.objects.filter(status=StagedProductImage.Status.WAITING)
        .filter(Q(hinted_code__iexact=code) | Q(extracted_codes__contains=[code]))
        .select_related("batch")
        .order_by("id")
    )
    claimed = skipped = 0
    batch_ids: set[int] = set()
    for staged in qs:
        img = _attach_staged_to_product(staged, product, user=user)
        batch_ids.add(staged.batch_id)
        if img:
            claimed += 1
        else:
            skipped += 1

    for bid in batch_ids:
        PhotoUploadBatch.objects.filter(pk=bid).first() and PhotoUploadBatch.objects.get(
            pk=bid
        ).refresh_counts()

    if claimed or skipped:
        # Record a small audit batch so history shows the auto-claim
        claim_batch = start_batch(
            user=user,
            mode=PhotoUploadBatch.Mode.CLAIM,
            source="auto_claim",
            note=f"Auto-claimed for {code} → product #{product.pk}",
            target_code=code,
        )
        claim_batch.files_total = claimed + skipped
        claim_batch.attached_count = claimed
        claim_batch.skipped_count = skipped
        claim_batch.save(
            update_fields=[
                "files_total",
                "attached_count",
                "skipped_count",
                "updated_at",
            ]
        )

    return {"claimed": claimed, "skipped": skipped, "product_id": product.pk, "code": code}


def assign_staged_photo(
    staged: StagedProductImage,
    code: str,
    *,
    user=None,
    stage_if_missing: bool = True,
) -> dict:
    """Manually point a waiting photo at a PJ / barcode."""
    code = normalize_code(code)
    if staged.status != StagedProductImage.Status.WAITING:
        return {"ok": False, "detail": f"Photo is {staged.status}, not waiting."}
    if not code:
        return {"ok": False, "detail": "Enter a PJ / barcode."}

    product = resolve_product_by_code(code)
    staged.hinted_code = code
    if code not in (staged.extracted_codes or []):
        codes = list(staged.extracted_codes or [])
        codes.insert(0, code)
        staged.extracted_codes = codes

    if product is None:
        if not stage_if_missing:
            return {"ok": False, "detail": f"No design found for {code}."}
        staged.status_detail = f"waiting for PJ: {code}"
        staged.save(
            update_fields=["hinted_code", "extracted_codes", "status_detail", "updated_at"]
        )
        return {
            "ok": True,
            "staged": True,
            "detail": f"Kept floating — will attach when {code} is added to stock.",
            "item": staged,
        }

    img = _attach_staged_to_product(staged, product, user=user)
    staged.batch.refresh_counts()
    return {
        "ok": True,
        "staged": False,
        "attached": bool(img),
        "skipped": img is None,
        "product_id": product.pk,
        "item": staged,
    }


def discard_staged_photo(staged: StagedProductImage, *, user=None) -> None:
    staged.status = StagedProductImage.Status.DISCARDED
    staged.status_detail = "discarded by user"
    staged.discarded_at = timezone.now()
    staged.discarded_by = user if getattr(user, "is_authenticated", False) else None
    staged.save(
        update_fields=[
            "status",
            "status_detail",
            "discarded_at",
            "discarded_by",
            "updated_at",
        ]
    )
    if staged.image:
        # keep file for history — do not delete
        pass
    staged.batch.refresh_counts()


def staged_public_dict(staged: StagedProductImage, request=None) -> dict:
    def _abs(url: str) -> str:
        if request and url:
            return request.build_absolute_uri(url)
        return url

    return {
        "id": staged.pk,
        "batch_id": staged.batch_id,
        "source_filename": staged.source_filename,
        "original_name": staged.original_name,
        "file_size": staged.file_size,
        "content_type": staged.content_type,
        "extracted_codes": staged.extracted_codes or [],
        "hinted_code": staged.hinted_code,
        "status": staged.status,
        "status_detail": staged.status_detail,
        "kind": staged.kind,
        "url": _abs(staged.image.url) if staged.image else "",
        "thumb_url": _abs(staged.display_url) if staged.display_url else "",
        "product_id": staged.product_id,
        "product_image_id": staged.product_image_id,
        "created_at": staged.created_at.isoformat() if staged.created_at else "",
        "attached_at": staged.attached_at.isoformat() if staged.attached_at else "",
    }
