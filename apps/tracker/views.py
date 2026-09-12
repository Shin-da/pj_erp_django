"""
Product Tracker — scan/reconciliation UI.

Ports `product_tracker_new.aspx` (see the legacy code-behind analysis for
the full original algorithm). Deliberate simplifications made for this
first version, vs. the legacy build:

  - Workflow is always "Scan only" here — the legacy "Transfer only" and
    "Scan + transfer" workflows (auto-moving company-stock items between
    locations as a side effect of a scan) are not implemented yet. Use
    the `transfers` app for transfers in the meantime.
  - A closing scan closes against exactly ONE opening session
    (`parent_session` is a single FK on TrackerSession already — legacy
    allowed multiple via a comma-string column, which doesn't map onto a
    normal FK). If you need to close multiple opening scans together,
    that needs a schema change (M2M) — flagging for later, not building
    it speculatively now.
  - CHECK mode is genuinely read-only here (no TrackerSession/
    TrackerScanItem rows are written) — matching what the legacy page's
    own on-screen help text claims. The legacy C# actually *does* write a
    session row in Check mode despite that help text; that looked like a
    bug, not a deliberate design, so it wasn't carried over. Flag if you
    actually want Check-item scans persisted for audit purposes.
  - ENTERED, for a closing scan, is the count of barcodes actually pasted
    today. The legacy version showed the *opening baseline* count under
    an "ENTERED" label while the audit log used the actual entered count
    for the same word — those disagreed with each other in the legacy
    code. This version uses one consistent, intuitive meaning.
  - No barcode-prefix ("must start with PJ") validation, no AJAX live
    validation, no Excel export yet, no double-submit idempotency key,
    no void/soft-delete of sessions. All straightforward additions later
    if wanted — not left out because they're hard, just not built yet.

Status classification uses `inventory.StockStatus` directly (PENDING /
ASSIGNED / SOLD / RESERVED / IN_TRANSIT) rather than the legacy's four
separate, only-partially-agreeing status columns — that reconciliation
already happened once, at import time (see django-rebuild-plan.md §13).
"""

import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.accounts.access import require_perm
from apps.inventory.models import ProductItem, StockStatus
from apps.locations.models import Location

from .models import ScanMode, ScanResult, TrackerScanItem, TrackerSession

import json

from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.http import JsonResponse
from django.views.decorators.http import require_POST


def _parse_barcodes(text):
    tokens = re.split(r"[\r\n,]+", text or "")
    seen = set()
    out = []
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        key = tok.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tok)
    return out


def _status_result(item):
    return {
        StockStatus.PENDING: ScanResult.COMPANY_STOCK,
        StockStatus.ASSIGNED: ScanResult.ASSIGNED,
        StockStatus.SOLD: ScanResult.SOLD,
        StockStatus.RESERVED: ScanResult.RESERVED,
        StockStatus.IN_TRANSIT: ScanResult.OTHER,
    }.get(item.status, ScanResult.OTHER)


@require_perm("tracker.add_trackersession")
def scan(request):
    locations = Location.objects.order_by("name")
    opening_sessions = (
        TrackerSession.objects.filter(mode=ScanMode.OPENING)
        .select_related("location")
        .order_by("-scan_index")[:50]
    )
    recent_sessions = (
        TrackerSession.objects.select_related("location", "created_by", "parent_session")
        .order_by("-scan_index")[:25]
    )

    context = {
        "locations": locations,
        "opening_sessions": opening_sessions,
        "recent_sessions": recent_sessions,
        "scan_type": request.POST.get("scan_type", "OPENING"),
        "location_id": request.POST.get("location_id", ""),
        "parent_id": request.POST.get("parent_id", ""),
        "barcode_text": request.POST.get("barcodes", ""),
        "result": None,
        "result_choices": ScanResult.choices,
        "entered": 0,
        "expected": 0,
        "expected_label": "",
    }

    if request.method == "POST":
        scan_type = request.POST.get("scan_type")
        location_id = request.POST.get("location_id")
        barcode_text = request.POST.get("barcodes", "")
        barcodes = _parse_barcodes(barcode_text)

        location = Location.objects.filter(pk=location_id).first() if location_id else None
        if scan_type in (ScanMode.OPENING, ScanMode.CLOSING) and not location:
            messages.error(request, "Pick a scan location first.")
            return render(request, "tracker/scan.html", context)
        if not barcodes:
            messages.error(request, "Paste at least one barcode.")
            return render(request, "tracker/scan.html", context)

        items_by_key = {
            i.barcode.lower(): i
            for i in ProductItem.objects.filter(barcode__in=barcodes).select_related("location", "product")
        }

        removed = []
        rows = []

        if scan_type == ScanMode.OPENING:
            at_location = []
            for bc in barcodes:
                item = items_by_key.get(bc.lower())
                if not item:
                    removed.append((bc, "Not found in the system"))
                    continue
                if item.location_id != location.id:
                    removed.append((bc, f"System has it at {item.location.code}, not {location.code}"))
                    continue
                at_location.append(item)

            expected_reference = ProductItem.objects.filter(
                location=location, status=StockStatus.PENDING
            ).count()

            session = TrackerSession.objects.create(
                mode=ScanMode.OPENING,
                location=location,
                created_by=request.user,
                item_count=len(at_location),
            )
            # Classify by the item's ACTUAL status, the same way closing
            # does. Previously every barcode scanned at the right location
            # was stamped COMPANY_STOCK regardless of whether the system
            # had it as sold, assigned or reserved — so a sold piece still
            # sitting in the case counted as company stock, while the
            # `expected` figure beside it counted PENDING only. The two
            # numbers were measuring different things and the operator had
            # no way to see it.
            for item in at_location:
                result = _status_result(item)
                TrackerScanItem.objects.create(
                    session=session, item=item, result=result, location_at_scan=location,
                )
                rows.append({"barcode": item.barcode, "product": item.product.name, "result": result, "extra": False})

            context["result"] = {
                "session": session,
                "entered": len(at_location),
                "expected": expected_reference,
                "expected_label": "company stock the system has here — anything scanned that is sold, assigned or reserved is listed below but not counted in this figure",
                "rows": rows,
                "removed": removed,
            }

        elif scan_type == ScanMode.CLOSING:
            parent_id = request.POST.get("parent_id")
            parent = (
                TrackerSession.objects.filter(pk=parent_id, mode=ScanMode.OPENING).first()
                if parent_id else None
            )
            if not parent:
                messages.error(request, "Pick an opening scan to close against.")
                return render(request, "tracker/scan.html", context)

            baseline_items = list(
                ProductItem.objects.filter(tracker_scans__session=parent).select_related("location", "product")
            )
            baseline_by_key = {i.barcode.lower(): i for i in baseline_items}
            entered_keys = {bc.lower() for bc in barcodes}

            session = TrackerSession.objects.create(
                mode=ScanMode.CLOSING,
                location=location,
                parent_session=parent,
                created_by=request.user,
                item_count=len(baseline_items),
            )

            for item in baseline_items:
                is_company_stock = item.status == StockStatus.PENDING
                at_scan_location = item.location_id == location.id
                key = item.barcode.lower()
                if key not in entered_keys and is_company_stock:
                    result = ScanResult.LOSS if at_scan_location else ScanResult.ELSEWHERE
                elif key in entered_keys and is_company_stock and not at_scan_location:
                    result = ScanResult.WRONG_LOCATION
                else:
                    result = _status_result(item)
                TrackerScanItem.objects.create(
                    session=session, item=item, result=result, location_at_scan=item.location,
                )
                rows.append({"barcode": item.barcode, "product": item.product.name, "result": result, "extra": False})

            for bc in barcodes:
                key = bc.lower()
                if key in baseline_by_key:
                    continue
                item = items_by_key.get(key)
                if not item:
                    rows.append({"barcode": bc, "product": "—", "result": ScanResult.NOT_FOUND, "extra": True})
                    continue
                is_company_stock = item.status == StockStatus.PENDING
                at_scan_location = item.location_id == location.id
                if is_company_stock and not at_scan_location:
                    result = ScanResult.WRONG_LOCATION
                else:
                    result = _status_result(item)
                TrackerScanItem.objects.create(
                    session=session, item=item, result=result, location_at_scan=item.location, is_extra=True,
                )
                rows.append({"barcode": item.barcode, "product": item.product.name, "result": result, "extra": True})

            context["result"] = {
                "session": session,
                "entered": len(barcodes),
                "expected": parent.item_count,
                "expected_label": f"from opening scan {parent}",
                "rows": rows,
                "removed": [],
            }

        elif scan_type == ScanMode.CHECK:
            for bc in barcodes:
                item = items_by_key.get(bc.lower())
                if not item:
                    rows.append({"barcode": bc, "product": "—", "result": ScanResult.NOT_FOUND, "extra": False})
                    continue
                is_company_stock = item.status == StockStatus.PENDING
                if location and is_company_stock and item.location_id != location.id:
                    result = ScanResult.WRONG_LOCATION
                else:
                    result = _status_result(item)
                rows.append({"barcode": item.barcode, "product": item.product.name, "result": result, "extra": False})

            context["result"] = {
                "session": None,
                "entered": len(barcodes),
                "expected": len(barcodes),
                "expected_label": "check item — nothing saved",
                "rows": rows,
                "removed": [],
            }

        else:
            messages.error(request, "Unknown scan type.")

    return render(request, "tracker/scan.html", context)

@require_perm("tracker.add_trackersession")
@require_POST
def validate_barcodes(request):
    """
    Called live (debounced) while the operator types/pastes into the
    barcode box. Mirrors the legacy ValidateBarcodes.ashx: strip anything
    not starting with "PJ", dedupe case-insensitively, check what's left
    against the database, and hand back the cleaned list plus why
    anything got dropped — all before the operator submits anything.
    """
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "bad request"}, status=400)

    raw = payload.get("raw", "")
    tokens = _parse_barcodes(raw)  # already dedupes case-insensitively

    prefix_invalid = [t for t in tokens if not t.lower().startswith("pj")]
    candidates = [t for t in tokens if t.lower().startswith("pj")]

    existing = set(
        ProductItem.objects.annotate(barcode_lower=Lower("barcode"))
        .filter(barcode_lower__in=[c.lower() for c in candidates])
        .values_list("barcode_lower", flat=True)
    )

    valid = [c for c in candidates if c.lower() in existing]
    not_found = [c for c in candidates if c.lower() not in existing]

    return JsonResponse({
        "normalized_text": "\n".join(valid),
        "removed_prefix": prefix_invalid,
        "removed_not_found": not_found,
    })

@require_perm("tracker.add_trackersession")
def expected_count(request):
    """
    Live "Expected" number for the gauge, before anything is submitted.
    Only meaningful for OPENING scans — the count of items the system
    currently has as company stock (PENDING) at the chosen location.
    Closing/Check don't need a server round-trip for this: Closing's
    expected is the opening session's saved item_count (already sitting on
    the parent-session <option> the operator picked), and Check's expected
    is just whatever was entered.
    """
    location_id = request.GET.get("location_id")
    if not location_id:
        return JsonResponse({"expected": 0})
    count = ProductItem.objects.filter(location_id=location_id, status=StockStatus.PENDING).count()
    return JsonResponse({"expected": count})

@login_required
def scan_preview(request):
    """
    PREVIEW ONLY — not wired to real scan/transfer/consignment logic.

    Mockup of the redesigned Product Tracker: five scan types (Inventory,
    Transfer, Room Allotment, Consignment, Return to Supplier — Return itself
    is still being worked out with the owner, so it's deliberately left off)
    plus a Scan/History tab split. History's location cards are real data
    (same query as inventory.location_list); everything scan-type-specific
    (reseller groups/clients, rooms, supplier "expected" counts) is hardcoded
    sample data below, clearly not real. Built so this can be walked through
    before any of it becomes real models or migrations.
    """
    locations = Location.objects.annotate(
        item_count=Count("items"),
        available_count=Count("items", filter=Q(items__status=StockStatus.PENDING)),
    ).order_by("name")

    # ---- Sample data below — preview only, not from the real database ----
    rooms = [f"Room {i}" for i in range(1, 12)]

    reseller_groups = [
        {"code": "GRP-A", "name": "Group A — Metro Manila", "clients": [
            {"code": "CO0012", "name": "Aliyah Santos"},
            {"code": "CO0031", "name": "Bea Reyes"},
        ]},
        {"code": "GRP-B", "name": "Group B — Visayas", "clients": [
            {"code": "CO0045", "name": "Carlo Dimaano"},
        ]},
        {"code": "GRP-C", "name": "Group C — Mindanao", "clients": [
            {"code": "CO0058", "name": "Divina Cruz"},
            {"code": "CO0061", "name": "Elmer Tan"},
        ]},
    ]

    suppliers = [
        {"code": "SUP-01", "name": "Alden Gems Co.", "expected": 42, "last_return": "Jul 30, 2026"},
        {"code": "SUP-02", "name": "Manila Metal Traders", "expected": 15, "last_return": "Aug 12, 2026"},
        {"code": "SUP-03", "name": "Cebu Stone Works", "expected": 8, "last_return": "—"},
    ]

    return render(request, "tracker/scan_preview.html", {
        "locations": locations,
        "rooms": rooms,
        "reseller_groups_json": json.dumps(reseller_groups),
        "suppliers_json": json.dumps(suppliers),
    })
