"""
ZPL (Zebra Programming Language) generation for the customizable label
designer.

The printer-setup preamble and the RFID-write command in `build_zpl` below
are kept from the legacy `PrintBarcode.aspx.cs` (`GenerateJewelleryZPL` and
its siblings) — those are printer/media-specific commands already proven
against Shin's Zebra hardware. Field placement is driven by editable
`LabelTemplate` + `LabelField` rows.
"""

import re
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
    "stone": "D-0.12/G-0.45",
    "colour": "Pink",
    "quality": "VS1",
    "weight": "3.25 g",
    "gross_weight": "3.80 g",
    "price": "15525",
    "price_rated": "15525",
    "currency": "USD",
    "size": "US 7",
    "company_name": COMPANY_NAME_DEFAULT,
    "static_text": "",
    "horizontal_line": "—",
}


def _fmt_money(amount):
    """Tag prices: whole number, rounded, no commas/decimals (e.g. 15525)."""
    if amount is None:
        return ""
    whole = Decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{int(whole)}"


def _fmt_weight(value):
    if value is None:
        return ""
    return f"{value:.2f} g"


_STONE_PREFIX_RE = re.compile(r"^[GD]\s*[-–—]?\s*", re.IGNORECASE)


def _stone_weight_prefix(metal_name="", category_code="", product_name="", reference_id=""):
    """
    Jewellery tags use G- for gold stone/metal weight and D- for diamond.
    Prefer explicit metal/name hints; SN (stone) category defaults to diamond.
    """
    blob = " ".join(
        str(part or "") for part in (metal_name, product_name, reference_id, category_code)
    ).lower()
    if any(token in blob for token in ("diamond", "dia", "diawt", "lab grown", "lab-grown")):
        return "D-"
    if category_code and str(category_code).upper() in {"SN", "ST", "SPP"}:
        return "D-"
    if any(token in blob for token in ("gold", "18k", "14k", "22k", "9k", "yg", "wg", "rg")):
        return "G-"
    if metal_name:
        return "G-"
    return "G-"


def _fmt_stone_weight(raw, metal_name="", category_code="", product_name="", reference_id=""):
    """Print stone weight as G-{value} or D-{value}."""
    text = (raw or "").strip()
    if not text:
        return ""
    # Drop a manual G-/D- so we never print G-G-…
    rest = _STONE_PREFIX_RE.sub("", text).strip()
    if not rest:
        return ""
    prefix = _stone_weight_prefix(metal_name, category_code, product_name, reference_id)
    return f"{prefix}{rest}"


def _fmt_stone_label(product):
    """Build tag stone line: D-{diamond} and/or G-{gold}, slash-separated."""
    parts = []
    diamond = (getattr(product, "diamond_weight", None) or "").strip()
    gold = (getattr(product, "gold_weight", None) or "").strip()
    legacy = (getattr(product, "stone", None) or "").strip()

    def clean(value):
        return _STONE_PREFIX_RE.sub("", value).strip()

    if diamond:
        rest = clean(diamond)
        if rest:
            parts.append(f"D-{rest}")
    if gold:
        rest = clean(gold)
        if rest:
            parts.append(f"G-{rest}")
    if parts:
        return "/".join(parts)
    # Fallback: legacy free-text stone column with metal-based prefix.
    if legacy:
        metal_name = product.metal.name if getattr(product, "metal_id", None) else ""
        purity_name = product.purity.name if getattr(product, "purity_id", None) else ""
        category_code = product.category.code if getattr(product, "category_id", None) else ""
        return _fmt_stone_weight(
            legacy,
            metal_name=metal_name or purity_name,
            category_code=category_code or "",
            product_name=product.name or "",
            reference_id=product.reference_id or "",
        )
    return ""


def resolve_field_values(item):
    """
    Build the {field_key: display_text} map for one real ProductItem.

    Stone prints as D-… / G-… from imported diamond_weight / gold_weight.
    Prices are whole numbers with no commas.
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
        "stone": _fmt_stone_label(product),
        "colour": (getattr(product, "colour", None) or "").strip(),
        "quality": (getattr(product, "quality", None) or "").strip(),
        "weight": _fmt_weight(product.net_weight),
        "gross_weight": _fmt_weight(product.gross_weight),
        "price": _fmt_money(price),
        "price_rated": _fmt_money(rated),
        "currency": product.currency.code if product.currency_id else "",
        "size": (getattr(product, "size", None) or "").strip(),
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
    if not text:
        return ""
    # Stone already carries G-/D- — ignore a redundant G/D prefix in static_text.
    if field.field_key == "stone":
        prefix = (field.static_text or "").strip()
        if prefix and re.fullmatch(r"[GD]\s*[-–—]?", prefix, flags=re.IGNORECASE):
            return text
    if field.static_text:
        # static_text doubles as an optional label/prefix on any field,
        # e.g. static_text="Price: " placed on the `price` field.
        return f"{field.static_text}{text}"
    return text


_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _zpl_escape(text):
    """
    Sanitize a payload for ^FD.

    ZPL treats ^ and ~ as command prefixes. Newlines/control chars must also
    be stripped — if they leak into the BrowserPrint payload (e.g. via
    Django escapejs turning \\n into the literal characters \\u000A), the
    printer prints garbage like \"RNu000A\" and can scramble following fields.
    """
    cleaned = (text or "").replace("^", "").replace("~", "").replace("\\", "")
    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    cleaned = _CTRL_RE.sub("", cleaned)
    return cleaned.strip()


def build_zpl(template, values):
    """
    Render one full ZPL label (^XA...^XZ) for `template` using a resolved
    {field_key: text} map from `resolve_field_values`.
    """
    # Continuous RFID stock: do NOT emit ^LL — legacy PrintBarcode.aspx.cs
    # never did, and a wrong length shifts the die-cut relative to the print.
    use_label_length = getattr(template, "media_profile", "") == "blank"

    lines = [
        "^XA",
        "^MFN,N",
        "^PR2,2,2",
        "~SD30",
        f"^PW{template.width_dots}",
    ]
    if use_label_length:
        lines.append(f"^LL{template.height_dots}")
    lines += [
        "^LH0,0",
        "^RS8,,,1,,,,",
        "^RFW,a,2,,A",
        f"^FD{_zpl_escape(values.get('barcode_number', ''))}",
        "^FS",
    ]

    ox = int(getattr(template, "offset_x", 0) or 0)
    oy = int(getattr(template, "offset_y", 0) or 0)

    for field in template.fields.filter(visible=True).order_by("order", "id"):
        x = max(0, field.x + ox)
        y = max(0, field.y + oy)

        if field.field_key == "barcode_image":
            barcode_value = _zpl_escape(values.get("barcode_number", ""))
            if not barcode_value:
                continue
            # Module width must be an integer on most Zebra firmware.
            bar_h = max(20, min(80, field.font_size * 2))
            lines.append(f"^FO{x},{y}^BY2,2^BCN,{bar_h},N,N,N,A^FD{barcode_value}")
            lines.append("^FS")
            continue

        if field.field_key == "horizontal_line":
            thickness = max(1, min(6, field.font_size // 10 or 1))
            lines.append(f"^FO{x},{y}^GB{field.box_width},{thickness},{thickness}^FS")
            continue

        text = _zpl_escape(render_field_text(field, values))
        if not text:
            continue

        font_h = field.font_size
        font_w = field.font_size + 4 if field.bold else field.font_size
        # Single-line field block; keep data on one ^FD line (no embedded newlines).
        lines.append(
            f"^FO{x},{y}^FB{field.box_width},1,,{field.align},^A0N,{font_h},{font_w}^FD{text}^FS"
        )

    lines.append("^PQ1,0,1,Y")
    lines.append("^XZ")
    # Join with real newlines for BrowserPrint; the print page must deliver
    # this string without escapejs turning them into literal \u000A text.
    return "\n".join(lines)
