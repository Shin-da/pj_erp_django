"""
Create reseller invoices (assignments) for HTML + write API.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.inventory.models import ProductItem, StockStatus

from .models import AssignmentMaster, DisplaySlot, DisplaySlotAllotment, Reseller


def create_invoice(
    *,
    reseller: Reseller,
    lines: list[dict],
    actor,
    is_reserve: bool = False,
    display_slot: DisplaySlot | None = None,
) -> AssignmentMaster:
    """
    ``lines`` entries: ``{barcode, unit_price, discount_percent?, commission_type?, commission_rate?}``.
    """
    if not lines:
        raise ValidationError("Scan at least one item onto this invoice before saving.")

    if display_slot is not None:
        active = (
            display_slot.allotments.filter(released_at__isnull=True)
            .select_related("reseller")
            .first()
        )
        if active and active.reseller_id != reseller.pk:
            raise ValidationError(
                f"{display_slot.name} is currently allotted to {active.reseller.name}."
            )

    prepared = []
    seen = set()
    barcodes = []
    for row in lines:
        barcode = (row.get("barcode") or "").strip()
        if not barcode:
            continue
        if barcode.lower() in seen:
            raise ValidationError(f"{barcode} was listed twice on this invoice.")
        seen.add(barcode.lower())
        barcodes.append(barcode)
        try:
            unit_price = Decimal(str(row.get("unit_price") or "0"))
            discount_percent = Decimal(str(row.get("discount_percent") or "0"))
            raw_rate = row.get("commission_rate")
            commission_rate = Decimal(str(raw_rate)) if raw_rate not in (None, "") else None
        except (InvalidOperation, TypeError) as exc:
            raise ValidationError(f"{barcode}: price, discount, or commission rate is invalid.") from exc
        if unit_price <= 0:
            raise ValidationError(f"{barcode}: unit price must be greater than 0.")
        prepared.append(
            {
                "barcode": barcode,
                "unit_price": unit_price,
                "discount_percent": discount_percent,
                "commission_type": (row.get("commission_type") or "")[:20],
                "commission_rate": commission_rate,
            }
        )

    if not prepared:
        raise ValidationError("Scan at least one item onto this invoice before saving.")

    with transaction.atomic():
        items = {
            i.barcode.lower(): i
            for i in ProductItem.objects.select_for_update()
            .filter(barcode__in=barcodes)
            .select_related("product")
        }
        master = AssignmentMaster.objects.create(
            reseller=reseller,
            is_reserve=is_reserve,
            display_slot=display_slot,
            created_by=actor,
        )
        for row in prepared:
            item = items.get(row["barcode"].lower())
            if not item:
                raise ValidationError(f"No item with barcode {row['barcode']!r}.")
            if item.status not in (StockStatus.PENDING, StockStatus.RESERVED):
                raise ValidationError(
                    f"{row['barcode']} is {item.status}, not eligible for assignment."
                )
            line = master.add_line(item, unit_price=row["unit_price"], actor=actor)
            line.discount_percent = row["discount_percent"]
            line.commission_type = row["commission_type"]
            line.commission_rate = row["commission_rate"]
            line.save()

        if display_slot and not display_slot.allotments.filter(
            released_at__isnull=True, reseller=reseller
        ).exists():
            DisplaySlotAllotment.objects.create(slot=display_slot, reseller=reseller)

    return master
