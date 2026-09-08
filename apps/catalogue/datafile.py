"""Pull print fields from the Tiara DATAFILE sheet onto pieces we already have.

Match is RFID Tag = barcode. This does not create pieces, and it does not
touch location, status, or price. A blank metal type is not stored as Silver.
"""

from __future__ import annotations

import csv
import io
import urllib.error
import urllib.request

from django.conf import settings
from django.db import transaction

from apps.catalogue.intake import infer_metal_name
from apps.catalogue.models import Metal, Purity, strip_dflt_prefix
from apps.inventory.models import ProductItem

TYPE_TO_METAL = {
    "YG": "Gold",
    "WG": "Gold",
    "RG": "Gold",
    "K18": "Gold",
    "K18Y": "Gold",
    "K18W": "Gold",
    "SL": "Silver",
    "S": "Silver",
    "SV": "Silver",
    "PT": "Platinum",
}


def sheet_url():
    sheet_id = getattr(settings, "DATAFILE_SHEET_ID", "1Nme3M7J5mW_cp21uA_nIhDF66xqKMkn9")
    gid = getattr(settings, "DATAFILE_SHEET_GID", "1206911768")
    return (
        "https://docs.google.com/spreadsheets/d/"
        f"{sheet_id}/export?format=csv&gid={gid}"
    )


def fetch_sheet_csv(url=None) -> str:
    target = url or sheet_url()
    req = urllib.request.Request(target, headers={"User-Agent": "pj-erp-datafile"})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.read().decode("utf-8-sig")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError(
                "The print sheet is not public. Set it to anyone with the link can view."
            ) from exc
        raise RuntimeError(f"Could not read the print sheet ({exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach the print sheet. {exc.reason}") from exc


def _weight(value: str):
    from apps.catalogue.intake import _decimal, _weight_text

    text = (value or "").strip().lower().replace("grams", "").replace("gram", "")
    text = text.replace("g", "").strip()
    number = _decimal(text)
    if number is None:
        return None, ""
    return number, _weight_text(str(number))


def metal_family(metal_type: str, purity: str) -> str:
    code = (metal_type or "").strip().upper()
    if code in TYPE_TO_METAL:
        return TYPE_TO_METAL[code]
    return infer_metal_name("", purity)


def parse_rows(csv_text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames or "RFID Tag" not in reader.fieldnames:
        raise RuntimeError("This is not the print sheet. Expected an RFID Tag column.")
    rows = []
    for raw in reader:
        tag = (raw.get("RFID Tag") or "").strip().upper()
        if not tag:
            continue
        purity = strip_dflt_prefix(raw.get("Metal Purity") or "")
        metal_type = (raw.get("Metal Type") or "").strip()
        net, net_text = _weight(raw.get("Net Weight") or "")
        metal_wt, metal_wt_text = _weight(raw.get("Metal Weight") or "")
        gross, _gross_text = _weight(raw.get("Gross Weight") or "")
        rows.append({
            "barcode": tag[:100],
            "purity": purity[:50],
            "metal_type": metal_type,
            "metal": metal_family(metal_type, purity),
            "net": net,
            "net_text": net_text,
            "metal_weight": metal_wt,
            "metal_weight_text": metal_wt_text,
            "gross": gross,
        })
    return rows


def _attach(product, row):
    fields = []
    if row["metal"]:
        metal, _ = Metal.objects.get_or_create(name=row["metal"][:100])
        if product.metal_id != metal.pk:
            product.metal = metal
            fields.append("metal")
    else:
        metal = product.metal
    if row["purity"] and metal:
        purity, _ = Purity.objects.get_or_create(metal=metal, name=row["purity"])
        if product.purity_id != purity.pk:
            product.purity = purity
            fields.append("purity")
    if row["net"] is not None and product.net_weight != row["net"]:
        product.net_weight = row["net"]
        fields.append("net_weight")
    gold = row["metal_weight_text"] or (row["net_text"] if not (product.gold_weight or "").strip() else "")
    if gold and product.gold_weight != gold:
        product.gold_weight = gold[:40]
        fields.append("gold_weight")
    if row["gross"] is not None and product.gross_weight != row["gross"]:
        product.gross_weight = row["gross"]
        fields.append("gross_weight")
    return fields


def apply_rows(rows: list[dict]) -> dict:
    updated = 0
    matched = 0
    missing = 0
    by_barcode = {}
    for row in rows:
        by_barcode.setdefault(row["barcode"], row)

    barcodes = list(by_barcode)
    for start in range(0, len(barcodes), 500):
        chunk = barcodes[start:start + 500]
        items = ProductItem.objects.filter(barcode__in=chunk).select_related(
            "product", "product__metal", "product__purity",
        )
        found = {item.barcode.upper(): item for item in items}
        with transaction.atomic():
            for barcode in chunk:
                item = found.get(barcode.upper())
                if item is None:
                    missing += 1
                    continue
                matched += 1
                fields = _attach(item.product, by_barcode[barcode])
                if fields:
                    fields.append("updated_at")
                    item.product.save(update_fields=fields)
                    updated += 1
    return {
        "sheet_rows": len(rows),
        "matched": matched,
        "updated": updated,
        "missing": missing,
    }


def sync_datafile() -> dict:
    return apply_rows(parse_rows(fetch_sheet_csv()))
