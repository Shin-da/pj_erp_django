"""
ZPL (Zebra Programming Language) generation for the customizable label
designer.

The printer-setup preamble and the RFID-write command in `build_zpl` below
are kept verbatim from the legacy `PrintBarcode.aspx.cs`
(`GenerateJewelleryZPL` and its siblings) — those are printer/media-specific
commands already proven against Shin's actual Zebra hardware, not legacy
cruft to redesign. Everything else is new: legacy hardcoded five fixed
field layouts directly in C#; this reads an editable `LabelTemplate` +
`LabelField` set instead. The field-placement math here has NOT been
verified against a physical printer yet — test a real print before relying
on a layout for daily use.
"""

COMPANY_NAME_DEFAULT = "PERFECT JEWELRY"

# Placeholder text shown in the designer canvas (no real product is loaded
# there) — purely a preview aid, never sent to a printer.
SAMPLE_FIELD_VALUES = {
    "barcode_number": "PJ000123",
    "barcode_image": "PJ000123",
    "reference_id": "REF-4821",
    "product_name": "Solitaire Ring",
    "metal": "Gold",
    "metal_purity": "18K",
    "stone": "Diamond",
    "colour": "Pink",
    "quality": "VS1",
    "weight": "3.25 g",
    "price": "12,500.00",
    "currency": "PHP",
    "size": "US 7",
    "company_name": COMPANY_NAME_DEFAULT,
    "static_text": "",
}


def resolve_field_values(item):
    """
    Build the {field_key: display_text} map for one real ProductItem.

    Colour/quality/stone/size aren't real columns on catalogue.ProductMaster
    yet — they were placeholder-mapped (or dropped) during the legacy data
    import (django-rebuild-plan.md §13's "known gaps"). Those fields
    resolve to an empty string here rather than a guess; you can still
    place them on a template, they'll just render blank until that data
    exists in the schema.
    """
    product = item.product
    metal_name = product.metal.name if product.metal_id else ""
    purity_name = product.purity.name if product.purity_id else ""
    weight = f"{product.net_weight:.2f} g" if product.net_weight is not None else ""
    price = f"{product.selling_price:,.2f}" if product.selling_price is not None else ""
    currency_code = product.currency.code if product.currency_id else ""

    return {
        "barcode_number": item.barcode,
        "barcode_image": item.barcode,
        "reference_id": product.reference_id or "",
        "product_name": product.name or "",
        "metal": metal_name,
        "metal_purity": purity_name,
        "stone": "",
        "colour": "",
        "quality": "",
        "weight": weight,
        "price": price,
        "currency": currency_code,
        "size": "",
        "company_name": COMPANY_NAME_DEFAULT,
        "static_text": "",
    }


def render_field_text(field, values):
    """Resolve one LabelField's on-label text given a resolved value map."""
    if field.field_key == "static_text":
        return field.static_text
    text = values.get(field.field_key, "")
    if field.static_text:
        # static_text doubles as an optional label/prefix on any field,
        # e.g. static_text="Price: " placed on the `price` field.
        return f"{field.static_text}{text}"
    return text


def _zpl_escape(text):
    # ZPL treats ^ and ~ as command-prefix characters even inside an ^FD
    # payload on some firmware — strip them rather than risk a caret in a
    # product name corrupting the label.
    return (text or "").replace("^", "").replace("~", "")


def build_zpl(template, values):
    """
    Render one full ZPL label (^XA...^XZ) for `template` using a resolved
    {field_key: text} map from `resolve_field_values`.
    """
    lines = [
        "^XA",
        "^MFN,N",
        "^PR2,2,2",
        "~SD30",
        f"^PW{template.width_dots}",
        "^LH0,0",
        "^RS8,,,1,,,,",
        "^RFW,a,2,,A",
        f"^FD{_zpl_escape(values.get('barcode_number', ''))}",
        "^FS",
    ]

    for field in template.fields.filter(visible=True).order_by("order", "id"):
        if field.field_key == "barcode_image":
            barcode_value = _zpl_escape(values.get("barcode_number", ""))
            if not barcode_value:
                continue
            lines.append(f"^FO{field.x},{field.y}^BY2,2^A0N,12,20^BCN,40,N,N,N,A^FD{barcode_value}")
            lines.append("^FS")
            continue

        text = _zpl_escape(render_field_text(field, values))
        if not text:
            continue

        font_h = field.font_size
        font_w = field.font_size + 6 if field.bold else field.font_size
        lines.append(
            f"^FO{field.x},{field.y}^FB{field.box_width},1,,{field.align},^A0N,{font_h},{font_w}^FD{text}"
        )
        lines.append("^FS")

    lines.append("^PQ1,0,1,Y")
    lines.append("^XZ")
    return "\n".join(lines)
