"""
Shared return-batch processing used by the HTML screen and the write API.

One atomic transaction for the whole batch — same rule as the legacy
ProductReturn fix: never leave a half-applied batch.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.assignment.models import AssignmentLine
from apps.inventory.models import InvalidStatusTransition, ProductItem, StockStatus

from .models import ReturnOutcome, ReturnRecord

OFFERED_OUTCOMES = [
    (ReturnOutcome.RETURN, "Returned to stock"),
    (ReturnOutcome.SOLD, "Confirmed sold"),
    (ReturnOutcome.RESERVE, "Moved to reserve"),
]

RETURNABLE_STATUSES = {StockStatus.ASSIGNED, StockStatus.RESERVED}

OUTCOMES_BY_STATUS = {
    StockStatus.ASSIGNED: {ReturnOutcome.RETURN, ReturnOutcome.SOLD, ReturnOutcome.RESERVE},
    StockStatus.RESERVED: {ReturnOutcome.RETURN},
}


def latest_line_for(item):
    return (
        AssignmentLine.objects.filter(item=item)
        .select_related("master", "master__reseller")
        .order_by("-master__created_at", "-id")
        .first()
    )


def process_return_batch(*, pairs: list[tuple[str, str]], actor) -> list[ReturnRecord]:
    """
    ``pairs`` is ``[(barcode, outcome), ...]``.
    Raises ``ValidationError`` / ``InvalidStatusTransition`` — nothing committed.
    """
    if not pairs:
        raise ValidationError("Nothing to process — provide at least one barcode.")

    valid_outcomes = {value for value, _ in OFFERED_OUTCOMES}
    normalized: list[tuple[str, str]] = []
    for barcode, outcome in pairs:
        barcode = (barcode or "").strip()
        if not barcode:
            continue
        if outcome not in valid_outcomes:
            raise ValidationError(f"{barcode}: {outcome!r} is not a supported outcome.")
        normalized.append((barcode, outcome))

    if not normalized:
        raise ValidationError("Nothing to process — provide at least one barcode.")

    records: list[ReturnRecord] = []
    with transaction.atomic():
        items = {
            i.barcode.lower(): i
            for i in ProductItem.objects.select_for_update()
            .filter(barcode__in=[b for b, _ in normalized])
            .select_related("product")
        }
        for barcode, outcome in normalized:
            item = items.get(barcode.lower())
            if not item:
                raise ValidationError(f"{barcode} is not in the system.")
            if item.status not in RETURNABLE_STATUSES:
                raise ValidationError(
                    f"{barcode} is {item.get_status_display().lower()} — nothing to return."
                )
            if outcome not in OUTCOMES_BY_STATUS.get(item.status, set()):
                label = dict(OFFERED_OUTCOMES).get(outcome, outcome)
                raise ValidationError(
                    f"{barcode} is {item.get_status_display().lower()} and cannot be "
                    f'marked "{label.lower()}" from that state.'
                )
            record = ReturnRecord.objects.create(
                item=item,
                assignment_line=latest_line_for(item),
                outcome=outcome,
                processed_by=actor,
            )
            record.process()
            records.append(record)
    return records
