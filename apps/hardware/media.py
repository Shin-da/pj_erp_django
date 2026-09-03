"""
Known RFID/jewellery label media profiles for the designer canvas.

Irys Standard RFID Tags (irysgroup.com): closed face 25×13 mm with a 50 mm
tail. When laid flat for printing the two faces sit stacked (front above
back) with the tail extending left from the body — total ~75×26 mm.

Dot math uses 203 DPI (Zebra desktop default, ≈8 dots/mm). Staff can still
override width/height per template; the profile mainly drives the outline
overlay so placement matches the physical die-cut.
"""

# ≈ dots per mm at 203 DPI (203 / 25.4)
_DPMM_203 = 203 / 25.4


def _mm(mm, dpi=203):
    return int(round(mm * dpi / 25.4))


def irys_standard(dpi=203):
    """Flat Irys Standard RFID jewellery tag at the given DPI.

    Die-cut (laid flat, print-side up):
      - Two 25×13 mm faces stacked (front on top, back below) with a fold
        between them.
      - A 50 mm tail with a pointed tip attached to the *front* face only —
        vertically centred on that face, not on the fold. After folding, the
        tail wraps the jewellery and the two faces stick together.
    """
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
                "hint": "On the front face only — wraps the jewellery when folded",
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
                "hint": "Other face when folded — no tail",
                "x": tail_w,
                "y": face_h,
                "w": face_w,
                "h": face_h,
            },
        ],
        # Die-cut silhouette including the pointed tail tip (printer still
        # uses a rectangular ^PW/^LL). Clockwise from the tip.
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


def blank_rectangle(width_dots=600, height_dots=208, dpi=203):
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


MEDIA_PROFILES = {
    "irys_standard": irys_standard(203),
    "blank": blank_rectangle(),
}


def get_media_profile(profile_id, width_dots=None, height_dots=None, dpi=203):
    if profile_id == "irys_standard":
        base = irys_standard(dpi or 203)
    else:
        base = blank_rectangle(
            width_dots=width_dots or 600,
            height_dots=height_dots or 208,
            dpi=dpi or 203,
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
                "width_mm": round(width_dots * 25.4 / (dpi or 203), 1),
                "height_mm": round(height_dots * 25.4 / (dpi or 203), 1),
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
        base = blank_rectangle(width_dots or base["width_dots"], height_dots or base["height_dots"], dpi or 203)
    return base


DEFAULT_MEDIA_PROFILE = "irys_standard"
