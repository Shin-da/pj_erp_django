import json
import re
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.access import require_any_perm, require_perm
from apps.inventory.models import ProductItem

from .media import DEFAULT_PRINTER_DPI, MEDIA_PROFILES, get_media_profile, irys_jewellery_sample_layout
from .models import LabelField, LabelPrintLog, LabelTemplate
from .zpl import SAMPLE_FIELD_VALUES, build_zpl, render_field_text, resolve_field_values

FIELD_LIST_VALUES = (
    "id", "field_key", "static_text", "x", "y", "font_size",
    "bold", "align", "box_width", "visible", "order",
)


def _region_at(geometry, x, y):
    """Return the die-cut region label covering (x, y), if any."""
    for r in (geometry or {}).get("regions") or []:
        if r["x"] <= x <= r["x"] + r["w"] and r["y"] <= y <= r["y"] + r["h"]:
            return r.get("label") or r.get("id") or ""
    return ""

# Palette order — matches how staff think about a jewellery tag.
FIELD_PALETTE_GROUPS = [
    ("Identity", [
        LabelField.FieldKey.SUPPLIER_CODE,
        LabelField.FieldKey.REFERENCE_ID,
        LabelField.FieldKey.BARCODE_NUMBER,
        LabelField.FieldKey.BARCODE_IMAGE,
        LabelField.FieldKey.PRODUCT_NAME,
        LabelField.FieldKey.SUBCATEGORY,
        LabelField.FieldKey.CATEGORY_CODE,
        LabelField.FieldKey.SUPPLIER_NAME,
    ]),
    ("Metal & stone", [
        LabelField.FieldKey.METAL,
        LabelField.FieldKey.METAL_PURITY,
        LabelField.FieldKey.COLOUR,
        LabelField.FieldKey.WEIGHT,
        LabelField.FieldKey.GROSS_WEIGHT,
        LabelField.FieldKey.STONE,
        LabelField.FieldKey.QUALITY,
        LabelField.FieldKey.SIZE,
    ]),
    ("Price & brand", [
        LabelField.FieldKey.PRICE,
        LabelField.FieldKey.PRICE_RATED,
        LabelField.FieldKey.CURRENCY,
        LabelField.FieldKey.COMPANY_NAME,
    ]),
    ("Design", [
        LabelField.FieldKey.STATIC_TEXT,
        LabelField.FieldKey.HORIZONTAL_LINE,
    ]),
]


def _parse_barcodes(raw):
    """Split on newline/comma, trim, dedupe case-insensitively, keep order."""
    seen = set()
    tokens = []
    for part in re.split(r"[\r\n,]+", raw or ""):
        token = part.strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        tokens.append(token)
    return tokens


def _field_choice_map():
    return {k: v for k, v in LabelField.FieldKey.choices}


@login_required
def template_list(request):
    templates = LabelTemplate.objects.all().prefetch_related("fields")
    return render(request, "hardware/template_list.html", {
        "templates": templates,
        "categories": LabelTemplate.Category.choices,
        "media_profiles": LabelTemplate.MediaProfile.choices,
    })


@require_perm("hardware.can_manage_labels")
@require_POST
def template_create(request):
    name = request.POST.get("name", "").strip() or "Untitled template"
    category = request.POST.get("category") or LabelTemplate.Category.ANY
    media_profile = request.POST.get("media_profile") or LabelTemplate.MediaProfile.IRYS_STANDARD
    tpl = LabelTemplate(name=name, category=category, media_profile=media_profile, created_by=request.user)
    tpl.apply_media_defaults()
    tpl.save()
    if tpl.media_profile == LabelTemplate.MediaProfile.IRYS_STANDARD:
        tpl.apply_jewellery_sample_layout()
    messages.success(request, f'Template "{tpl.name}" created — design it below.')
    return redirect("hardware:template_edit", pk=tpl.pk)


@require_perm("hardware.can_manage_labels")
@require_POST
def template_duplicate(request, pk):
    src = get_object_or_404(LabelTemplate, pk=pk)
    with transaction.atomic():
        clone = LabelTemplate.objects.create(
            name=f"{src.name} (copy)",
            category=src.category,
            media_profile=src.media_profile,
            dpi=src.dpi,
            width_dots=src.width_dots,
            height_dots=src.height_dots,
            created_by=request.user,
        )
        for f in src.fields.all():
            f.pk = None
            f.id = None
            f.template = clone
            f.save()
    messages.success(request, f'Duplicated "{src.name}" as "{clone.name}".')
    return redirect("hardware:template_edit", pk=clone.pk)


@require_perm("hardware.can_manage_labels")
@require_POST
def template_delete(request, pk):
    tpl = get_object_or_404(LabelTemplate, pk=pk)
    name = tpl.name
    tpl.delete()
    messages.success(request, f'Template "{name}" deleted.')
    return redirect("hardware:template_list")


@require_perm("hardware.can_manage_labels")
def template_edit(request, pk):
    tpl = get_object_or_404(LabelTemplate, pk=pk)
    fields = list(tpl.fields.order_by("order", "id").values(*FIELD_LIST_VALUES))
    geometry = tpl.media_geometry()
    choice_map = _field_choice_map()
    palette = [
        {
            "group": group,
            "fields": [{"key": key.value, "label": choice_map[key.value]} for key in keys],
        }
        for group, keys in FIELD_PALETTE_GROUPS
    ]
    return render(request, "hardware/template_edit.html", {
        "template_obj": tpl,
        "categories": LabelTemplate.Category.choices,
        "media_profiles": LabelTemplate.MediaProfile.choices,
        "fields_json": json.dumps(fields),
        "field_choices": LabelField.FieldKey.choices,
        "palette_groups": palette,
        "sample_values_json": json.dumps(SAMPLE_FIELD_VALUES),
        "geometry_json": json.dumps(geometry),
        "media_profiles_json": json.dumps({
            pid: get_media_profile(pid, dpi=tpl.dpi or DEFAULT_PRINTER_DPI)
            for pid in MEDIA_PROFILES
        }),
        "sample_layout_json": json.dumps(irys_jewellery_sample_layout(tpl.dpi or DEFAULT_PRINTER_DPI)),
    })


@require_perm("hardware.can_manage_labels")
@require_POST
def template_save(request, pk):
    tpl = get_object_or_404(LabelTemplate, pk=pk)
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "bad request"}, status=400)

    valid_keys = {k for k, _ in LabelField.FieldKey.choices}
    valid_align = {k for k, _ in LabelField.Align.choices}
    valid_media = {k for k, _ in LabelTemplate.MediaProfile.choices}

    with transaction.atomic():
        name = payload.get("name")
        if name:
            tpl.name = name.strip() or tpl.name

        category = payload.get("category")
        if category:
            tpl.category = category

        if "is_default" in payload:
            is_default = bool(payload.get("is_default"))
            if is_default:
                LabelTemplate.objects.filter(category=tpl.category).exclude(pk=tpl.pk).update(is_default=False)
            tpl.is_default = is_default

        media_profile = payload.get("media_profile")
        if media_profile in valid_media:
            tpl.media_profile = media_profile

        # Field coords in the payload are already in the chosen DPI space
        # (designer rescales client-side when DPI changes).
        if "dpi" in payload:
            try:
                tpl.dpi = max(100, min(600, int(payload.get("dpi") or tpl.dpi)))
            except (TypeError, ValueError):
                pass

        for attr in ("offset_x", "offset_y"):
            if attr in payload:
                try:
                    setattr(tpl, attr, max(-800, min(800, int(payload.get(attr) or 0))))
                except (TypeError, ValueError):
                    pass

        resize_to_profile = bool(payload.get("resize_to_profile"))
        if resize_to_profile:
            tpl.apply_media_defaults()
        else:
            if "width_dots" in payload:
                try:
                    tpl.width_dots = max(40, min(2000, int(payload.get("width_dots") or tpl.width_dots)))
                except (TypeError, ValueError):
                    pass
            if "height_dots" in payload:
                try:
                    tpl.height_dots = max(40, min(2000, int(payload.get("height_dots") or tpl.height_dots)))
                except (TypeError, ValueError):
                    pass

        tpl.save()

        incoming_fields = payload.get("fields", [])
        keep_ids = []
        for order, f in enumerate(incoming_fields):
            field_key = f.get("field_key") or LabelField.FieldKey.STATIC_TEXT
            if field_key not in valid_keys:
                field_key = LabelField.FieldKey.STATIC_TEXT
            align = f.get("align") or LabelField.Align.LEFT
            if align not in valid_align:
                align = LabelField.Align.LEFT

            defaults = dict(
                field_key=field_key,
                static_text=f.get("static_text") or "",
                x=max(0, int(f.get("x") or 0)),
                y=max(0, int(f.get("y") or 0)),
                font_size=max(8, min(120, int(f.get("font_size") or 18))),
                bold=bool(f.get("bold", False)),
                align=align,
                box_width=max(10, min(2000, int(f.get("box_width") or 180))),
                visible=bool(f.get("visible", True)),
                order=order,
            )
            field_id = f.get("id")
            if field_id and int(field_id) > 0:
                LabelField.objects.filter(pk=field_id, template=tpl).update(**defaults)
                keep_ids.append(int(field_id))
            else:
                new_field = LabelField.objects.create(template=tpl, **defaults)
                keep_ids.append(new_field.pk)

        tpl.fields.exclude(pk__in=keep_ids).delete()

    geometry = tpl.media_geometry()
    return JsonResponse({
        "ok": True,
        "fields": list(tpl.fields.order_by("order", "id").values(*FIELD_LIST_VALUES)),
        "width_dots": tpl.width_dots,
        "height_dots": tpl.height_dots,
        "dpi": tpl.dpi,
        "media_profile": tpl.media_profile,
        "offset_x": tpl.offset_x,
        "offset_y": tpl.offset_y,
        "geometry": geometry,
    })


@require_any_perm("hardware.can_print_label", "hardware.can_reprint_label")
def print_labels(request):
    templates = LabelTemplate.objects.all()
    selected_template_id = ""
    context = {
        "templates": templates,
        "barcode_text": "",
        "preview_items": None,
        "zpl_data": "",
        "product_count": 0,
        "not_found": [],
        "selected_template_id": selected_template_id,
        "print_payload": [],
    }

    if request.method == "POST":
        barcode_text = request.POST.get("barcodes", "")
        template_id = request.POST.get("template_id", "")
        tokens = _parse_barcodes(barcode_text)
        context["barcode_text"] = barcode_text
        context["selected_template_id"] = template_id

        items = (
            ProductItem.objects.filter(barcode__in=tokens)
            .select_related(
                "product",
                "product__category",
                "product__metal",
                "product__purity",
                "product__currency",
                "product__supplier",
            )
        )
        items_by_barcode = {i.barcode.lower(): i for i in items}

        chosen_template = None
        if template_id:
            chosen_template = LabelTemplate.objects.filter(pk=template_id).prefetch_related("fields").first()

        default_by_category = {
            t.category: t for t in LabelTemplate.objects.filter(is_default=True).prefetch_related("fields")
        }

        preview_items = []
        zpl_chunks = []
        not_found = []
        skipped_no_template = []

        for token in tokens:
            item = items_by_barcode.get(token.lower())
            if not item:
                not_found.append(token)
                continue

            tpl = (
                chosen_template
                or default_by_category.get(item.product.category.code)
                or default_by_category.get(LabelTemplate.Category.ANY)
            )
            if not tpl:
                skipped_no_template.append(token)
                continue

            values = resolve_field_values(item)
            zpl_chunks.append(build_zpl(tpl, values))
            geometry = tpl.media_geometry()
            ox = int(getattr(tpl, "offset_x", 0) or 0)
            oy = int(getattr(tpl, "offset_y", 0) or 0)
            preview_fields = []
            blank_keys = []
            for f in tpl.fields.filter(visible=True).order_by("order", "id"):
                # Preview is die-cut WYSIWYG: place fields at design coords so
                # zones match the physical tag. Offset X/Y is printer registration
                # applied only in ZPL (TOF → die-cut), not a layout shift on-tag.
                dx, dy = f.x, f.y
                px, py = max(0, dx + ox), max(0, dy + oy)
                region = _region_at(geometry, dx, dy)
                if f.field_key == "horizontal_line":
                    preview_fields.append({
                        "key": f.field_key,
                        "label": f.get_field_key_display(),
                        "text": "",
                        "x": dx,
                        "y": dy,
                        "print_x": px,
                        "print_y": py,
                        "font_size": f.font_size,
                        "bold": f.bold,
                        "align": f.align,
                        "box_width": f.box_width,
                        "is_line": True,
                        "is_barcode": False,
                        "barcode_height": 0,
                        "blank": False,
                        "region": region,
                    })
                    continue
                text = render_field_text(f, values)
                if not text and f.field_key != "barcode_image":
                    blank_keys.append(f.get_field_key_display())
                    continue
                barcode_height = 0
                if f.field_key == "barcode_image":
                    # Match apps.hardware.zpl.build_zpl bar height.
                    barcode_height = max(20, min(80, f.font_size * 2))
                preview_fields.append({
                    "key": f.field_key,
                    "label": f.get_field_key_display(),
                    "text": text,
                    "x": dx,
                    "y": dy,
                    "print_x": px,
                    "print_y": py,
                    "font_size": f.font_size,
                    "bold": f.bold,
                    "align": f.align,
                    "box_width": f.box_width,
                    "is_line": False,
                    "is_barcode": f.field_key == "barcode_image",
                    "barcode_height": barcode_height,
                    "blank": False,
                    "region": region,
                })

            preview_items.append({
                "barcode": item.barcode,
                "template_name": tpl.name,
                "template_id": tpl.pk,
                "width_dots": tpl.width_dots,
                "height_dots": tpl.height_dots,
                "dpi": tpl.dpi,
                "width_mm": geometry.get("width_mm"),
                "height_mm": geometry.get("height_mm"),
                "media_profile": tpl.media_profile,
                "offset_x": ox,
                "offset_y": oy,
                "geometry": geometry,
                "fields": preview_fields,
                "blank_fields": blank_keys,
                "print_count": 0,
                "last_printed_at": None,
            })

        if skipped_no_template:
            messages.warning(
                request,
                f"No template available for: {', '.join(skipped_no_template)} "
                "(pick a template explicitly, or set a default for that category).",
            )

        barcodes = [p["barcode"] for p in preview_items]
        if barcodes:
            counts = {
                row["barcode"]: row
                for row in (
                    LabelPrintLog.objects.filter(
                        barcode__in=barcodes,
                        status=LabelPrintLog.Status.SUCCESS,
                    )
                    .values("barcode")
                    .annotate(times=Count("id"), qty=Sum("quantity"))
                )
            }
            last_by = {}
            for log in LabelPrintLog.objects.filter(
                barcode__in=barcodes,
                status=LabelPrintLog.Status.SUCCESS,
            ).order_by("-created_at"):
                if log.barcode not in last_by:
                    last_by[log.barcode] = log.created_at
            for p in preview_items:
                info = counts.get(p["barcode"])
                if info:
                    p["print_count"] = int(info["qty"] or info["times"] or 0)
                p["last_printed_at"] = last_by.get(p["barcode"])

        context["preview_items"] = preview_items
        context["not_found"] = not_found
        context["zpl_data"] = "\n".join(zpl_chunks)
        context["product_count"] = len(preview_items)
        context["print_payload"] = [
            {"barcode": p["barcode"], "template_id": p["template_id"]}
            for p in preview_items
        ]

    return render(request, "hardware/print.html", context)


@require_any_perm("hardware.can_print_label", "hardware.can_reprint_label")
@require_POST
def print_log(request):
    """Record labels after BrowserPrint reports send success or failure."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "bad request"}, status=400)

    raw_items = payload.get("items") or []
    if not raw_items and payload.get("barcodes"):
        raw_items = [{"barcode": b} for b in payload.get("barcodes") or []]
    if not isinstance(raw_items, list) or not raw_items:
        return JsonResponse({"ok": False, "error": "no items"}, status=400)

    status = payload.get("status") or LabelPrintLog.Status.SUCCESS
    if status not in {LabelPrintLog.Status.SUCCESS, LabelPrintLog.Status.ERROR}:
        status = LabelPrintLog.Status.SUCCESS
    printer_name = (payload.get("printer_name") or "")[:200]
    error_message = (payload.get("error_message") or "")[:300]
    default_template_id = payload.get("template_id") or None

    barcodes = []
    for row in raw_items[:500]:
        if isinstance(row, str):
            bc = row.strip()
            tid = default_template_id
        else:
            bc = (row.get("barcode") or "").strip()
            tid = row.get("template_id") or default_template_id
        if bc:
            barcodes.append((bc, tid))

    if not barcodes:
        return JsonResponse({"ok": False, "error": "no barcodes"}, status=400)

    # First print vs reprint: prior successful send requires can_reprint_label.
    user = request.user
    if not user.is_superuser:
        prior_ok = set(
            LabelPrintLog.objects.filter(
                barcode__in=[b for b, _ in barcodes],
                status=LabelPrintLog.Status.SUCCESS,
            ).values_list("barcode", flat=True)
        )
        prior_lower = {b.lower() for b in prior_ok}
        needs_reprint = any(bc.lower() in prior_lower for bc, _ in barcodes)
        needs_first = any(bc.lower() not in prior_lower for bc, _ in barcodes)
        if needs_reprint and not user.has_perm("hardware.can_reprint_label"):
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Reprint requires hardware.can_reprint_label — ask Owner/Admin.",
                },
                status=403,
            )
        if needs_first and not user.has_perm("hardware.can_print_label"):
            return JsonResponse(
                {
                    "ok": False,
                    "error": "First print requires hardware.can_print_label — ask Owner/Admin.",
                },
                status=403,
            )

    items_by_bc = {
        i.barcode.lower(): i
        for i in ProductItem.objects.filter(barcode__in=[b for b, _ in barcodes])
    }
    template_ids = {tid for _, tid in barcodes if tid}
    if default_template_id:
        template_ids.add(default_template_id)
    templates = {
        t.pk: t
        for t in LabelTemplate.objects.filter(pk__in=[int(x) for x in template_ids if str(x).isdigit()])
    }

    batch_id = uuid.uuid4()
    rows = []
    for barcode, tid in barcodes:
        item = items_by_bc.get(barcode.lower())
        tpl = None
        if tid is not None:
            try:
                tpl = templates.get(int(tid))
            except (TypeError, ValueError):
                tpl = None
        rows.append(
            LabelPrintLog(
                batch_id=batch_id,
                barcode=item.barcode if item else barcode[:100],
                item=item,
                template=tpl,
                template_name=(tpl.name if tpl else "")[:100],
                printed_by=request.user if request.user.is_authenticated else None,
                printer_name=printer_name,
                quantity=1,
                status=status,
                error_message=error_message if status == LabelPrintLog.Status.ERROR else "",
            )
        )

    LabelPrintLog.objects.bulk_create(rows)
    return JsonResponse({"ok": True, "batch_id": str(batch_id), "logged": len(rows)})


@login_required
def print_history(request):
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    logs = LabelPrintLog.objects.select_related("printed_by", "template", "item").all()
    if q:
        logs = logs.filter(barcode__icontains=q)
    if status in {LabelPrintLog.Status.SUCCESS, LabelPrintLog.Status.ERROR}:
        logs = logs.filter(status=status)

    summary = None
    if q:
        success = LabelPrintLog.objects.filter(
            barcode__icontains=q,
            status=LabelPrintLog.Status.SUCCESS,
        )
        summary = success.aggregate(times=Count("id"), qty=Sum("quantity"))

    paginator = Paginator(logs, 50)
    page = paginator.get_page(request.GET.get("page") or 1)

    return render(request, "hardware/print_history.html", {
        "page": page,
        "q": q,
        "status": status,
        "summary": summary,
    })
