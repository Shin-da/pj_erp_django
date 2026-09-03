"""
ZPL (Zebra Programming Language) generation for the customizable label
designer.

The printer-setup preamble and the RFID-write command in `build_zpl` below
are kept verbatim from the legacy `PrintBarcode.aspx.cs`
(`GenerateJewelleryZPL` and its siblings) — those are printer/media-specific
commands already proven against Shin's actual Zebra hardware, not legacy
cruft to redesign. Everything else is new: legacy hardcoded five fixed
field layouts directly in C#; this reads an editable `LabelTemplate` +
`LabelField` set instead.
"""

from decimal import Decimal, ROUND_HALF_UP

COMPANY_NAME_DEFAULT = "PERFECT JEWELRY"

# Placeholder text shown in the designer canvas (no real product is loaded
# there) — purely a preview aid, never sent to a printer.
SAMPLE_FIELD_VALUES = {
    "barcode_number": "PJ21258",
    "barcode_image": "PJ21258",
    "reference_id": "ER858LE1",
    "product_name": "Solitaire Ring",
    "supplier_code": "BNG",
    "supplier_name": "Bangalore Supply",
    "subcategory": "BR",
    "category_code": "JW",
    "metal": "Gold",
    "metal_purity": "18K",
    "stone": "0.12 / 0.45",
    "colour": "Pink",
    "quality": "VS1",
    "weight": "3.25 g",
    "gross_weight": "3.80 g",
    "price": "15,525.00",
    "price_rated": "15,525.00",
    "currency": "USD",
    "size": "US 7",
    "company_name": COMPANY_NAME_DEFAULT,
    "static_text": "",
    "horizontal_line": "—",
}


def _fmt_money(amount):
    if amount is None:
        return ""
    return f"{amount:,.2f}"


def _fmt_weight(value):
    if value is None:
        return ""
    return f"{value:.2f} g"


def resolve_field_values(item):
    """
    Build the {field_key: display_text} map for one real ProductItem.

    Colour / quality / stone / size are not real columns on
    catalogue.ProductMaster yet (legacy import gaps). Those keys resolve
    to empty strings rather than invented placeholders — you can still
    place them on a template; they'll print blank until that data exists.
    """
    product = item.product
    metal_name = product.metal.name if product.metal_id else ""
    purity_name = product.purity.name if product.purity_id else ""
    supplier = product.supplier
    supplier_code = ""
    supplier_name = ""
    if supplier:
        supplier_code = (supplier.reference_code or "").strip() or (supplier.name or "")[:12]
        supplier_name = supplier.name or ""

    price = product.selling_price
    rate = product.effective_rate if hasattr(product, "effective_rate") else Decimal("1")
    if rate is None:
        rate = Decimal("1")
    rated = None
    if price is not None:
        rated = (price * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    category_code = ""
    if product.category_id:
        category_code = product.category.code or ""

    return {
        "barcode_number": item.barcode or "",
        "barcode_image": item.barcode or "",
        "reference_id": product.reference_id or "",
        "product_name": product.name or "",
        "supplier_code": supplier_code,
        "supplier_name": supplier_name,
        "subcategory": product.subcategory or "",
        "category_code": category_code,
        "metal": metal_name,
        "metal_purity": purity_name,
        "stone": "",
        "colour": "",
        "quality": "",
        "weight": _fmt_weight(product.net_weight),
        "gross_weight": _fmt_weight(product.gross_weight),
        "price": _fmt_money(price),
        "price_rated": _fmt_money(rated),
        "currency": product.currency.code if product.currency_id else "",
        "size": "",
        "company_name": COMPANY_NAME_DEFAULT,
        "static_text": "",
        "horizontal_line": "",
    }


def render_field_text(field, values):
    """Resolve one LabelField's on-label text given a resolved value map."""
    if field.field_key == "static_text":
        return field.static_text
    if field.field_key == "horizontal_line":
        return "—"
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
        f"^LL{template.height_dots}",
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
            # Height scales with font_size so the designer control is meaningful.
            bar_h = max(20, min(80, field.font_size * 2))
            lines.append(
                f"^FO{field.x},{field.y}^BY1.5,2^BCN,{bar_h},N,N,N,A^FD{barcode_value}"
            )
            lines.append("^FS")
            continue

        if field.field_key == "horizontal_line":
            # Graphic box 1-dot tall = hairline across box_width.
            thickness = max(1, min(6, field.font_size // 10 or 1))
            lines.append(f"^FO{field.x},{field.y}^GB{field.box_width},{thickness},{thickness}^FS")
            continue

        text = _zpl_escape(render_field_text(field, values))
        if not text:
            continue

        font_h = field.font_size
        font_w = field.font_size + 4 if field.bold else field.font_size
        lines.append(
            f"^FO{field.x},{field.y}^FB{field.box_width},1,,{field.align},^A0N,{font_h},{font_w}^FD{text}"
        )
        lines.append("^FS")

    lines.append("^PQ1,0,1,Y")
    lines.append("^XZ")
    return "\n".join(lines)
