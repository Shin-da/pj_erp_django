"""
Known RFID/jewellery label media profiles for the designer canvas.

Irys Standard RFID Tags (irysgroup.com): closed face 25×13 mm with a 50 mm
tail. When laid flat for printing the two faces sit stacked (front above
back) with the tail extending left from the *front* face only —
total ~75×26 mm.

Dot math must match the printer DPI. Zebra jewellery RFID desktops
(ZD621R etc.) are commonly **300 DPI**; using 203 DPI coords on a 300 DPI
printer compresses both faces into the top panel (exactly the mis-print we
saw). Staff can still override width/height per template.
"""


def _mm(mm, dpi=300):
    return int(round(mm * dpi / 25.4))


def irys_standard(dpi=300):
    """Flat Irys Standard RFID jewellery tag at the given DPI.

    Die-cut (laid flat, print-side up):
      - Two 25×13 mm faces stacked (front on top, back below) with a fold
        between them.
      - A 50 mm tail with a pointed tip attached to the *front* face only —
        vertically centred on that face, not on the fold. After folding, the
        tail wraps the jewellery and the two faces stick together.
    """
    dpi = int(dpi or 300)
    tail_w = _mm(50, dpi)
    face_w = _mm(25, dpi)
    face_h = _mm(13, dpi)
    width = tail_w + face_w
    height = face_h * 2
    # Thin strip, centred on the FRONT face (not the whole tag / fold).
    tail_h = _mm(4, dpi)
    tail_y = (face_h - tail_h) // 2
    tip_w = _mm(6, dpi)
    return {
        "id": "irys_standard",
        "label": "Irys Standard RFID (25×13 mm closed + 50 mm tail)",
        "dpi": dpi,
        "width_mm": round(width * 25.4 / dpi, 1),
        "height_mm": round(height * 25.4 / dpi, 1),
        "width_dots": width,
        "height_dots": height,
        "regions": [
            {
                "id": "tail",
                "label": "Tail",
                "hint": "On the front face only - wraps the jewellery when folded",
                "x": 0,
                "y": tail_y,
                "w": tail_w,
                "h": tail_h,
            },
            {
                "id": "front",
                "label": "Front",
                "hint": "Face the tail is attached to (visible when folded)",
                "x": tail_w,
                "y": 0,
                "w": face_w,
                "h": face_h,
            },
            {
                "id": "back",
                "label": "Back",
                "hint": "Other face when folded - no tail",
                "x": tail_w,
                "y": face_h,
                "w": face_w,
                "h": face_h,
            },
        ],
        # Die-cut silhouette including the pointed tail tip (printer still
        # uses a rectangular ^PW). Clockwise from the tip.
        "outline": [
            [0, tail_y + tail_h // 2],
            [tip_w, tail_y],
            [tail_w, tail_y],
            [tail_w, 0],
            [width, 0],
            [width, height],
            [tail_w, height],
            [tail_w, tail_y + tail_h],
            [tip_w, tail_y + tail_h],
        ],
        "fold_y": face_h,
    }


def blank_rectangle(width_dots=None, height_dots=None, dpi=300):
    dpi = int(dpi or 300)
    # Default blank ≈ Irys outer box at this DPI so switching profiles feels natural.
    if width_dots is None or height_dots is None:
        irys = irys_standard(dpi)
        width_dots = width_dots or irys["width_dots"]
        height_dots = height_dots or irys["height_dots"]
    return {
        "id": "blank",
        "label": "Blank rectangle (free design)",
        "dpi": dpi,
        "width_mm": round(width_dots * 25.4 / dpi, 1),
        "height_mm": round(height_dots * 25.4 / dpi, 1),
        "width_dots": width_dots,
        "height_dots": height_dots,
        "regions": [
            {
                "id": "body",
                "label": "Label",
                "hint": "Full printable area",
                "x": 0,
                "y": 0,
                "w": width_dots,
                "h": height_dots,
            },
        ],
        "outline": [
            [0, 0],
            [width_dots, 0],
            [width_dots, height_dots],
            [0, height_dots],
        ],
        "fold_y": None,
    }


# Catalog entry uses 300 DPI — matches typical ZD621R jewellery RFID units.
MEDIA_PROFILES = {
    "irys_standard": irys_standard(300),
    "blank": blank_rectangle(dpi=300),
}


def get_media_profile(profile_id, width_dots=None, height_dots=None, dpi=300):
    dpi = int(dpi or 300)
    if profile_id == "irys_standard":
        base = irys_standard(dpi)
    else:
        base = blank_rectangle(
            width_dots=width_dots,
            height_dots=height_dots,
            dpi=dpi,
        )
    # Honour explicit canvas size overrides while keeping region ratios for Irys.
    if profile_id == "irys_standard" and width_dots and height_dots:
        if width_dots != base["width_dots"] or height_dots != base["height_dots"]:
            sx = width_dots / base["width_dots"]
            sy = height_dots / base["height_dots"]
            base = {
                **base,
                "width_dots": width_dots,
                "height_dots": height_dots,
                "width_mm": round(width_dots * 25.4 / dpi, 1),
                "height_mm": round(height_dots * 25.4 / dpi, 1),
                "regions": [
                    {
                        **r,
                        "x": int(round(r["x"] * sx)),
                        "y": int(round(r["y"] * sy)),
                        "w": int(round(r["w"] * sx)),
                        "h": int(round(r["h"] * sy)),
                    }
                    for r in base["regions"]
                ],
                "outline": [
                    [int(round(x * sx)), int(round(y * sy))]
                    for x, y in base["outline"]
                ],
                "fold_y": int(round(base["fold_y"] * sy)) if base["fold_y"] is not None else None,
            }
    elif profile_id == "blank":
        base = blank_rectangle(width_dots or base["width_dots"], height_dots or base["height_dots"], dpi)
    return base


DEFAULT_MEDIA_PROFILE = "irys_standard"
DEFAULT_PRINTER_DPI = 300

# Zebra jewellery RFID continuous stock registration nudges at 300 DPI.
# Positive Y shifts print down; negative X shifts print left onto the die-cut.
IRYS_REGISTRATION_OFFSET_Y_300 = 55
IRYS_REGISTRATION_OFFSET_X_300 = -18


def irys_registration_offset_y(dpi=None):
    dpi = int(dpi or DEFAULT_PRINTER_DPI)
    return int(round(IRYS_REGISTRATION_OFFSET_Y_300 * dpi / DEFAULT_PRINTER_DPI))


def irys_registration_offset_x(dpi=None):
    dpi = int(dpi or DEFAULT_PRINTER_DPI)
    return int(round(IRYS_REGISTRATION_OFFSET_X_300 * dpi / DEFAULT_PRINTER_DPI))


def irys_jewellery_sample_layout(dpi=None):
    """Canonical jewellery tag layout for Irys Standard (print-accurate).

    Design coordinates are relative to the die-cut (what preview shows).
    `offset_y` is printer registration only (added in ZPL). Tuned so:
      Tail  — subcategory centred in the strip
      Front — SKU, price, divider (clear of the fold)
      Back  — PJ#, barcode, category, company (barcode fully below the fold)
    """
    dpi = int(dpi or DEFAULT_PRINTER_DPI)
    geo = irys_standard(dpi)
    front = next(r for r in geo["regions"] if r["id"] == "front")
    back = next(r for r in geo["regions"] if r["id"] == "back")
    tail = next(r for r in geo["regions"] if r["id"] == "tail")
    s = dpi / DEFAULT_PRINTER_DPI

    def ds(n):
        return max(1, int(round(n * s)))

    # Keep type small enough for 25×13 mm faces at 300 DPI.
    sub_font = ds(22)
    tail_pad = max(2, (tail["h"] - sub_font) // 2)

    fields = [
        {
            "field_key": "subcategory",
            "x": ds(80),
            "y": tail["y"] + tail_pad,
            "font_size": sub_font,
            "bold": True,
            "align": "C",
            "box_width": max(ds(80), tail["w"] - ds(110)),
        },
        {
            "field_key": "reference_id",
            "x": front["x"] + ds(8),
            "y": front["y"] + ds(8),
            "font_size": ds(20),
            "bold": True,
            "align": "L",
            "box_width": front["w"] - ds(16),
        },
        {
            "field_key": "price_rated",
            "x": front["x"] + ds(8),
            "y": front["y"] + ds(40),
            "font_size": ds(24),
            "bold": True,
            "align": "C",
            "box_width": front["w"] - ds(16),
        },
        {
            "field_key": "horizontal_line",
            "x": front["x"] + ds(8),
            "y": front["y"] + ds(76),
            "font_size": ds(12),
            "bold": False,
            "align": "L",
            "box_width": front["w"] - ds(16),
        },
        {
            "field_key": "barcode_number",
            "x": back["x"] + ds(8),
            "y": back["y"] + ds(10),
            "font_size": ds(20),
            "bold": True,
            "align": "L",
            "box_width": back["w"] - ds(16),
        },
        {
            "field_key": "barcode_image",
            "x": back["x"] + ds(8),
            "y": back["y"] + ds(38),
            "font_size": ds(20),
            "bold": False,
            "align": "L",
            "box_width": back["w"] - ds(16),
        },
        {
            "field_key": "category_code",
            "x": back["x"] + ds(8),
            "y": back["y"] + ds(90),
            "font_size": ds(14),
            "bold": False,
            "align": "L",
            "box_width": ds(60),
        },
        {
            "field_key": "company_name",
            "x": back["x"] + ds(8),
            "y": back["y"] + ds(112),
            "font_size": ds(14),
            "bold": True,
            "align": "C",
            "box_width": back["w"] - ds(16),
        },
    ]
    return {
        "geometry": geo,
        "fields": fields,
        "offset_y": irys_registration_offset_y(dpi),
        "offset_x": irys_registration_offset_x(dpi),
        "width_dots": geo["width_dots"],
        "height_dots": geo["height_dots"],
        "dpi": dpi,
    }


def scale_dot(value, from_dpi, to_dpi):
    """Scale a single dot measurement between DPI settings."""
    from_dpi = int(from_dpi or DEFAULT_PRINTER_DPI)
    to_dpi = int(to_dpi or DEFAULT_PRINTER_DPI)
    if from_dpi == to_dpi:
        return int(value or 0)
    return int(round((int(value or 0) * to_dpi) / from_dpi))
