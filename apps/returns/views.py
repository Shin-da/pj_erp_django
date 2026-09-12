"""
Returns — the counter workflow for stock coming back in.

Replaces `ProductReturn.aspx`. The legacy page's structural bug was that
`btnSave_Click` called `return_product_by_barcode()` on every pending
barcode *first* and only then decided whether the piece was actually
being reserved or reassigned (`ProductReturn.aspx.cs` ~653, ~702-703) —
so a reserved piece passed through a returned state in the same postback,
and a cancel approval afterwards could return it a second time. Nothing
here works that way: `ReturnRecord.process()` performs exactly one
transition per piece, chosen up front, and this view is a thin shell
around it.

Shape of the screen: scan or paste a batch of barcodes, the page resolves
each one live (who holds it, which invoice, what the system thinks its
status is), the operator sets an outcome per piece or for the whole
batch, and one POST processes them together.

REASSIGN is deliberately NOT offered here. `ReturnRecord.process()`
records it as an audit row without changing status, expecting the caller
to create the replacement AssignmentLine separately — so exposing it as
a one-click outcome would leave the piece assigned to the old reseller
with nothing on screen saying so. Build it when the "assign to whom"
step is designed; until then the outcome list is the three that are
complete.
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.assignment.models import InvoiceStatus
from apps.inventory.models import InvalidStatusTransition, ProductItem

from .models import ReturnRecord
from .services import (
    OFFERED_OUTCOMES,
    OUTCOMES_BY_STATUS,
    RETURNABLE_STATUSES,
    latest_line_for,
    process_return_batch,
)

# Re-export names used by templates / helpers (single source: services.py).


def _latest_line_for(item):
    return latest_line_for(item)


def _describe(item):
    """One barcode's worth of context for the scan table."""
    line = _latest_line_for(item)
    allowed = OUTCOMES_BY_STATUS.get(item.status, set())
    return {
        "ok": item.status in RETURNABLE_STATUSES,
        "allowed_outcomes": [
            {"value": value, "label": label} for value, label in OFFERED_OUTCOMES if value in allowed
        ],
        "barcode": item.barcode,
        "product": item.product.name,
        "status": item.get_status_display(),
        "status_code": item.status,
        "location": item.location.name,
        "holder": line.master.reseller.name if line else "",
        "holder_id": line.master.reseller_id if line else None,
        "invoice": line.master.invoice_number if line else "",
        "invoice_id": line.master_id if line else None,
        "invoice_cancelled": bool(line and line.master.invoice_status == InvoiceStatus.CANCELLED),
        "error": "" if item.status in RETURNABLE_STATUSES else (
            f"{item.barcode} is {item.get_status_display().lower()} — nothing to return."
        ),
    }


@login_required
def return_scan(request):
    recent = (
        ReturnRecord.objects.select_related(
            "item", "item__product", "processed_by", "assignment_line__master__reseller"
        )
        .order_by("-created_at")[:25]
    )
    return render(request, "returns/return_scan.html", {
        "outcomes": OFFERED_OUTCOMES,
        "recent": recent,
        "outcomes_json": json.dumps([{"value": v, "label": l} for v, l in OFFERED_OUTCOMES]),
    })


@login_required
def item_lookup(request):
    """
    One barcode in, one JSON answer out, for the live scan table. Mirrors
    `assignment.item_lookup` deliberately — same shape, different
    eligibility rule — so the two scan fields behave identically to an
    operator using both.
    """
    barcode = request.GET.get("barcode", "").strip()
    if not barcode:
        return JsonResponse({"ok": False, "error": "No barcode given."})

    item = (
        ProductItem.objects.filter(barcode__iexact=barcode)
        .select_related("product", "location")
        .first()
    )
    if not item:
        return JsonResponse({"ok": False, "barcode": barcode, "error": f"No item with barcode {barcode}."})

    return JsonResponse(_describe(item))


@login_required
@require_POST
def process_returns(request):
    """
    Process a whole batch in ONE transaction. Either every piece the
    operator confirmed comes back, or none of them do and the page says
    which one failed — a half-applied batch is the state that makes
    physical stock and the system disagree, and it is exactly what the
    legacy page produced when a mid-loop error left earlier barcodes
    already returned.
    """
    barcodes = request.POST.getlist("barcode")
    outcomes = request.POST.getlist("outcome")

    if not barcodes:
        messages.error(request, "Nothing to process — scan at least one barcode.")
        return redirect("returns:return_scan")

    if len(barcodes) != len(outcomes):
        messages.error(request, "The form didn't submit cleanly — please re-scan and try again.")
        return redirect("returns:return_scan")

    valid_outcomes = {value for value, _ in OFFERED_OUTCOMES}
    pairs = []
    for barcode, outcome in zip(barcodes, outcomes):
        barcode = barcode.strip()
        if not barcode:
            continue
        if outcome not in valid_outcomes:
            messages.error(request, f"{barcode}: {outcome!r} is not an outcome this screen can process.")
            return redirect("returns:return_scan")
        pairs.append((barcode, outcome))

    if not pairs:
        messages.error(request, "Nothing to process — scan at least one barcode.")
        return redirect("returns:return_scan")

    try:
        records = process_return_batch(pairs=pairs, actor=request.user)
    except (ValidationError, InvalidStatusTransition) as exc:
        detail = exc.messages[0] if isinstance(exc, ValidationError) else str(exc)
        messages.error(request, f"Nothing was processed. {detail}")
        return redirect("returns:return_scan")

    processed = len(records)
    messages.success(request, f"Processed {processed} piece{'' if processed == 1 else 's'}.")
    return redirect("returns:return_scan")
