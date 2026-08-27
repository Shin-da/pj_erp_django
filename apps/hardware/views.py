import json
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.inventory.models import ProductItem

from .models import LabelField, LabelTemplate
from .zpl import SAMPLE_FIELD_VALUES, build_zpl, render_field_text, resolve_field_values

FIELD_LIST_VALUES = ("id", "field_key", "static_text", "x", "y", "font_size", "bold", "align", "box_width", "visible", "order")


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


@login_required
def template_list(request):
    templates = LabelTemplate.objects.all().prefetch_related("fields")
    return render(request, "hardware/template_list.html", {
        "templates": templates,
        "categories": LabelTemplate.Category.choices,
    })


@login_required
@require_POST
def template_create(request):
    name = request.POST.get("name", "").strip() or "Untitled template"
    category = request.POST.get("category") or LabelTemplate.Category.ANY
    tpl = LabelTemplate.objects.create(name=name, category=category, created_by=request.user)
    messages.success(request, f'Template "{tpl.name}" created — design it below.')
    return redirect("hardware:template_edit", pk=tpl.pk)


@login_required
@require_POST
def template_duplicate(request, pk):
    src = get_object_or_404(LabelTemplate, pk=pk)
    with transaction.atomic():
        clone = LabelTemplate.objects.create(
            name=f"{src.name} (copy)", category=src.category,
            width_dots=src.width_dots, height_dots=src.height_dots, created_by=request.user,
        )
        for f in src.fields.all():
            f.pk = None
            f.id = None
            f.template = clone
            f.save()
    messages.success(request, f'Duplicated "{src.name}" as "{clone.name}".')
    return redirect("hardware:template_edit", pk=clone.pk)


@login_required
@require_POST
def template_delete(request, pk):
    tpl = get_object_or_404(LabelTemplate, pk=pk)
    name = tpl.name
    tpl.delete()
    messages.success(request, f'Template "{name}" deleted.')
    return redirect("hardware:template_list")


@login_required
def template_edit(request, pk):
    tpl = get_object_or_404(LabelTemplate, pk=pk)
    fields = list(tpl.fields.order_by("order", "id").values(*FIELD_LIST_VALUES))
    return render(request, "hardware/template_edit.html", {
        "template_obj": tpl,
        "categories": LabelTemplate.Category.choices,
        "fields_json": json.dumps(fields),
        "field_choices": LabelField.FieldKey.choices,
        "sample_values_json": json.dumps(SAMPLE_FIELD_VALUES),
    })


@login_required
@require_POST
def template_save(request, pk):
    tpl = get_object_or_404(LabelTemplate, pk=pk)
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "bad request"}, status=400)

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

        tpl.save()

        incoming_fields = payload.get("fields", [])
        keep_ids = []
        for order, f in enumerate(incoming_fields):
            field_id = f.get("id")
            defaults = dict(
                field_key=f.get("field_key") or LabelField.FieldKey.STATIC_TEXT,
                static_text=f.get("static_text") or "",
                x=int(f.get("x") or 0),
                y=int(f.get("y") or 0),
                font_size=int(f.get("font_size") or 24),
                bold=bool(f.get("bold", False)),
                align=f.get("align") or LabelField.Align.LEFT,
                box_width=int(f.get("box_width") or 300),
                visible=bool(f.get("visible", True)),
                order=order,
            )
            if field_id and int(field_id) > 0:
                LabelField.objects.filter(pk=field_id, template=tpl).update(**defaults)
                keep_ids.append(int(field_id))
            else:
                new_field = LabelField.objects.create(template=tpl, **defaults)
                keep_ids.append(new_field.pk)

        tpl.fields.exclude(pk__in=keep_ids).delete()

    return JsonResponse({
        "ok": True,
        "fields": list(tpl.fields.order_by("order", "id").values(*FIELD_LIST_VALUES)),
    })


@login_required
def print_labels(request):
    templates = LabelTemplate.objects.all()
    context = {
        "templates": templates,
        "barcode_text": "",
        "preview_items": None,
        "zpl_data": "",
        "product_count": 0,
        "not_found": [],
    }

    if request.method == "POST":
        barcode_text = request.POST.get("barcodes", "")
        template_id = request.POST.get("template_id", "")
        tokens = _parse_barcodes(barcode_text)
        context["barcode_text"] = barcode_text

        items = (
            ProductItem.objects.filter(barcode__in=tokens)
            .select_related("product", "product__category", "product__metal", "product__purity", "product__currency")
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
            preview_items.append({
                "barcode": item.barcode,
                "template_name": tpl.name,
                "fields": [
                    {"key": f.field_key, "text": render_field_text(f, values)}
                    for f in tpl.fields.filter(visible=True).order_by("order", "id")
                    if render_field_text(f, values)
                ],
            })

        if skipped_no_template:
            messages.warning(
                request,
                f"No template available for: {', '.join(skipped_no_template)} "
                "(pick a template explicitly, or set a default for that category).",
            )

        context["preview_items"] = preview_items
        context["not_found"] = not_found
        context["zpl_data"] = "\n".join(zpl_chunks)
        context["product_count"] = len(preview_items)

    return render(request, "hardware/print.html", context)
