"""Named label layouts restored on every deploy.

Earlier Irys data migrations deleted every field on every `irys_standard`
template, which is why designer work vanished after migrate. These specs are
the source of truth for layouts that must exist on live Postgres (`pj_erp_db`)
as well as the local catalogs.

If the operator changes the layout in the designer, dump it back into this
file — `ensure_label_templates` overwrites the named row on boot.
"""

JEFFFFFFF_NAME = "jefffffff"

JEFFFFFFF = {
    "name": JEFFFFFFF_NAME,
    "category": "ANY",
    "is_default": True,
    "media_profile": "irys_standard",
    "dpi": 300,
    "width_dots": 886,
    "height_dots": 308,
    "offset_x": -35,
    "offset_y": 55,
    "fields": [
        {
            "field_key": "subcategory",
            "x": 604,
            "y": 272,
            "font_size": 30,
            "box_width": 250,
            "align": "L",
            "bold": True,
            "visible": True,
            "static_text": "",
        },
        {
            "field_key": "reference_id",
            "x": 599,
            "y": 8,
            "font_size": 28,
            "box_width": 277,
            "align": "L",
            "bold": True,
            "visible": True,
            "static_text": "",
        },
        {
            "field_key": "price_rated",
            "x": 600,
            "y": 126,
            "font_size": 24,
            "box_width": 279,
            "align": "C",
            "bold": True,
            "visible": True,
            "static_text": "",
        },
        {
            "field_key": "barcode_number",
            "x": 599,
            "y": 164,
            "font_size": 35,
            "box_width": 279,
            "align": "L",
            "bold": True,
            "visible": True,
            "static_text": "",
        },
        {
            "field_key": "barcode_image",
            "x": 599,
            "y": 205,
            "font_size": 20,
            "box_width": 279,
            "align": "L",
            "bold": False,
            "visible": True,
            "static_text": "",
        },
        {
            "field_key": "metal_purity",
            "x": 601,
            "y": 47,
            "font_size": 25,
            "box_width": 90,
            "align": "L",
            "bold": False,
            "visible": True,
            "static_text": "",
        },
        {
            "field_key": "weight",
            "x": 599,
            "y": 77,
            "font_size": 25,
            "box_width": 90,
            "align": "L",
            "bold": False,
            "visible": True,
            "static_text": "",
        },
        {
            "field_key": "product_name",
            "x": 368,
            "y": 60,
            "font_size": 34,
            "box_width": 174,
            "align": "R",
            "bold": False,
            "visible": True,
            "static_text": "",
        },
        {
            "field_key": "colour",
            "x": 783,
            "y": 47,
            "font_size": 16,
            "box_width": 90,
            "align": "L",
            "bold": False,
            "visible": True,
            "static_text": "",
        },
    ],
}

SAVED_TEMPLATES = (JEFFFFFFF,)


def upsert_saved_template(LabelTemplate, LabelField, spec):
    """Create or replace one named template. Does not touch other templates."""
    name = spec["name"]
    tpl = LabelTemplate.objects.filter(name=name).order_by("id").first()
    created = tpl is None
    if tpl is None:
        tpl = LabelTemplate(name=name)

    tpl.category = spec["category"]
    tpl.is_default = bool(spec.get("is_default"))
    tpl.media_profile = spec["media_profile"]
    tpl.dpi = spec["dpi"]
    tpl.width_dots = spec["width_dots"]
    tpl.height_dots = spec["height_dots"]
    tpl.offset_x = spec["offset_x"]
    tpl.offset_y = spec["offset_y"]
    tpl.save()

    if tpl.is_default:
        LabelTemplate.objects.filter(category=tpl.category, is_default=True).exclude(pk=tpl.pk).update(
            is_default=False
        )

    LabelField.objects.filter(template_id=tpl.pk).delete()
    for order, row in enumerate(spec["fields"]):
        LabelField.objects.create(
            template_id=tpl.pk,
            field_key=row["field_key"],
            static_text=row.get("static_text") or "",
            x=int(row["x"]),
            y=int(row["y"]),
            font_size=int(row["font_size"]),
            bold=bool(row["bold"]),
            align=row["align"],
            box_width=int(row["box_width"]),
            visible=bool(row.get("visible", True)),
            order=order,
        )
    return tpl, created


def ensure_saved_templates(LabelTemplate=None, LabelField=None):
    if LabelTemplate is None or LabelField is None:
        from apps.hardware.models import LabelField, LabelTemplate
    return [upsert_saved_template(LabelTemplate, LabelField, spec) for spec in SAVED_TEMPLATES]
