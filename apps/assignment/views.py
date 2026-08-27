"""
Reseller directory — groups, and the clients under each — plus the
invoice list/detail/create pages.

Read-only pages, mirroring the shape of the product master pages:

  group_list     — every reseller group with its client count and how much
                   stock its clients are currently holding, plus the
                   ungrouped clients so nobody quietly falls off the page.
  group_detail   — one group: its clients, each with their own live counts.
  client_detail  — one client (a `Reseller` row): what they're holding right
                   now, their assignment/invoice history, and any display
                   slot allotted to them.

"Currently holding" is derived, never stored: it's the set of ProductItems
whose latest assignment belongs to this client and whose status is still
ASSIGNED. There is deliberately no `Reseller.items_held` counter to drift
out of sync — the legacy system's habit of denormalising counts into
columns that nothing kept updated is precisely the bug class the rebuild
is trying to leave behind.

  invoice_list / invoice_detail / invoice_create / invoice_stamp — the
  master/detail invoice screen requested 27 Aug 2026, built after the
  commission fields on AssignmentLine (see that model's docstring), aiming
  at the same list-on-the-left/detail-on-the-right interaction pj-accounting
  uses on its own Invoices page (public/index.html #page-invoices,
  public/app.js loadInvoices()/openInvoice()) — plain server-rendered
  Django here instead of its JS/SPA + REST API, and no separate invoice
  document: "creating an invoice" IS creating an AssignmentMaster with its
  lines, same as everywhere else in this app.

  item_lookup — added when the invoice_create form was redesigned around
  how items are actually added on the floor: scan a barcode, it appears,
  scan the next one — not type-a-price-per-row. Mirrors the legacy
  Rfid_scan.aspx flow (screenshot walkthrough, 27 Aug 2026), corrected the
  same way the rest of this app corrects legacy behavior:
    - Unit price is pulled from ProductMaster.selling_price the moment
      the barcode resolves, not retyped (the legacy "Total Price" field
      was never clearly tied to a per-item catalog price).
    - "Reseller Location" on the legacy form reads, from a fresh look,
      like a mislabelled "which company location are you scanning
      stock from" field, not a property of the reseller — so it's
      rebuilt here as a plain `locations.Location` picker that scanned
      barcodes are checked against (a real location-aware check, unlike
      the location-blind handheld-scanner bug already on file for
      `hardware`). Flagged to confirm with the business rather than
      assumed silently.
    - "Room No. pops" once reseller/location/type/date are chosen —
      this is the room-allotment coupling already modeled as
      `DisplaySlot`/`DisplaySlotAllotment` (see AssignmentMaster's
      docstring); invoice_create now actually offers it and records the
      allotment, instead of the field existing on the model unused.
    - "Select Date" (backdating the transaction) is NOT implemented yet
      — AssignmentMaster has no separate transaction-date field, only
      created_at. Deliberately left out rather than guessed at.
    - Gold-weight commission auto-calc from a scan is explicitly out of
      scope for this pass ("the gold logic... thats later," 27 Aug
      2026) — commission_type/commission_rate stay manually set per
      line for now, same as before this redesign.
"""

import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.inventory.models import ProductItem, StockStatus
from apps.locations.models import Location

from .models import (
    AssignmentMaster,
    CommissionType,
    DisplaySlot,
    DisplaySlotAllotment,
    InvoiceStatus,
    Reseller,
    ResellerGroup,
)


def _client_annotations():
    """Live per-client rollups, computed in the same query as the list."""
    return {
        "assignment_count": Count("assignments", distinct=True),
        "open_assignment_count": Count(
            "assignments",
            filter=Q(assignments__invoice_status=InvoiceStatus.DRAFT),
            distinct=True,
        ),
        "items_held": Count(
            "assignments__lines__item",
            filter=Q(assignments__lines__item__status=StockStatus.ASSIGNED),
            distinct=True,
        ),
    }


@login_required
def group_list(request):
    groups = ResellerGroup.objects.annotate(
        client_count=Count("clients", distinct=True),
        active_client_count=Count("clients", filter=Q(clients__is_active=True), distinct=True),
        items_held=Count(
            "clients__assignments__lines__item",
            filter=Q(clients__assignments__lines__item__status=StockStatus.ASSIGNED),
            distinct=True,
        ),
    ).order_by("name")

    q = request.GET.get("q", "").strip()
    if q:
        groups = groups.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(clients__name__icontains=q)).distinct()

    ungrouped = (
        Reseller.objects.filter(group__isnull=True)
        .annotate(**_client_annotations())
        .order_by("name")
    )
    if q:
        ungrouped = ungrouped.filter(Q(name__icontains=q) | Q(reference_code__icontains=q))

    return render(request, "assignment/group_list.html", {
        "groups": groups,
        "ungrouped": ungrouped,
        "q": q,
        "total_clients": Reseller.objects.count(),
    })


@login_required
def group_detail(request, pk):
    group = get_object_or_404(ResellerGroup, pk=pk)

    clients = Reseller.objects.filter(group=group).annotate(**_client_annotations()).order_by("name")

    q = request.GET.get("q", "").strip()
    if q:
        clients = clients.filter(Q(name__icontains=q) | Q(reference_code__icontains=q))

    return render(request, "assignment/group_detail.html", {
        "group": group,
        "clients": clients,
        "q": q,
        "items_held_total": sum(c.items_held for c in clients),
    })


@login_required
def client_detail(request, pk):
    client = get_object_or_404(
        Reseller.objects.select_related("group").annotate(**_client_annotations()), pk=pk
    )

    held = (
        ProductItem.objects.filter(
            assignment_lines__master__reseller=client,
            status=StockStatus.ASSIGNED,
        )
        .select_related("product", "product__currency", "location")
        .distinct()
        .order_by("barcode")
    )

    held_value = held.aggregate(total=Sum("product__selling_price"))["total"]

    paginator = Paginator(held, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    assignments = (
        AssignmentMaster.objects.filter(reseller=client)
        .annotate(line_count=Count("lines", distinct=True))
        .select_related("display_slot", "created_by")
        .order_by("-created_at")[:25]
    )

    slots = (
        DisplaySlotAllotment.objects.filter(reseller=client)
        .select_related("slot")
        .order_by("-created_at")[:10]
    )

    return render(request, "assignment/client_detail.html", {
        "client": client,
        "page_obj": page_obj,
        "held_value": held_value,
        "assignments": assignments,
        "slots": slots,
    })


@login_required
def invoice_list(request, pk=None):
    """
    Master/detail invoice screen — the list on the left is always the
    current search/filter result set; the detail on the right is whichever
    invoice's URL (`/resellers/invoices/<pk>/`) was requested, or empty on
    the bare `/resellers/invoices/` listing. Two URLs, one view, one
    template — see urls.py.
    """
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    invoices = (
        AssignmentMaster.objects.select_related("reseller")
        .annotate(
            line_count=Count("lines", distinct=True),
            # Discount-blind on purpose — cheap for a list of 30 rows.
            # The detail view below sums calculate_line_total() instead,
            # which is the real, discount-aware total.
            list_amount=Sum("lines__unit_price"),
        )
        .order_by("-created_at")
    )
    if q:
        invoices = invoices.filter(Q(invoice_number__icontains=q) | Q(reseller__name__icontains=q))
    if status:
        invoices = invoices.filter(invoice_status=status)

    paginator = Paginator(invoices, 30)
    page_obj = paginator.get_page(request.GET.get("page"))

    selected = None
    if pk:
        selected = get_object_or_404(
            AssignmentMaster.objects.select_related("reseller", "display_slot", "created_by"), pk=pk
        )
        selected.line_list = list(
            selected.lines.select_related("item", "item__product", "item__product__currency").order_by("id")
        )
        selected.amount_total = sum((line.calculate_line_total() for line in selected.line_list), Decimal("0"))
        selected.commission_total = sum((line.commission_value for line in selected.line_list), Decimal("0"))

    slots = list(DisplaySlot.objects.order_by("name"))
    for slot in slots:
        active = slot.allotments.filter(released_at__isnull=True).select_related("reseller").first()
        slot.occupant = active.reseller.name if active else None

    # Preview only — AssignmentMaster.invoice_number is derived from the
    # row's own pk at save() time (models.py's _generated_invoice_number),
    # not a separately reserved sequence, so this is "what it'll almost
    # certainly be" rather than a hold on the number. Fine for a form
    # preview; the real number is still decided at save time regardless
    # of what was shown here.
    last_id = AssignmentMaster.all_objects.order_by("-pk").values_list("pk", flat=True).first() or 0
    next_assignment_id = last_id + 1

    return render(request, "assignment/invoice_list.html", {
        "page_obj": page_obj,
        "q": q,
        "status": status,
        "selected": selected,
        "resellers": Reseller.objects.filter(is_active=True).order_by("name"),
        "locations": Location.objects.order_by("name"),  # SoftDeleteModel — objects manager already excludes deleted rows
        "display_slots": slots,
        "next_assignment_id": next_assignment_id,
        "commission_types": CommissionType.choices,
        "commission_types_json": json.dumps(list(CommissionType.choices)),
        "status_choices": InvoiceStatus.choices,
    })


@login_required
def item_lookup(request):
    """
    Backs the scan-to-add barcode field in the "+ New invoice" form.
    One barcode in, one JSON answer out: eligible + its product name +
    catalog unit price, or a reason it can't go on this invoice. This is
    the browser-typed equivalent of what a handheld scanner POSTs to
    `hardware` — same eligibility rule (PENDING/RESERVED only), plus an
    explicit location check the legacy Rfid_scan.aspx page didn't
    reliably do (see `hardware`'s scoped-TODO for the handheld path's
    own location-blind bug).
    """
    barcode = request.GET.get("barcode", "").strip()
    location_id = request.GET.get("location", "").strip()

    if not barcode:
        return JsonResponse({"ok": False, "error": "No barcode given."})

    try:
        item = ProductItem.objects.select_related("product", "product__currency", "location").get(barcode=barcode)
    except ProductItem.DoesNotExist:
        return JsonResponse({"ok": False, "error": f"No item with barcode {barcode!r}."})

    if item.status not in (StockStatus.PENDING, StockStatus.RESERVED):
        return JsonResponse({
            "ok": False,
            "error": f"{barcode} is {item.get_status_display()}, not eligible for assignment.",
        })

    if location_id:
        location = get_object_or_404(Location, pk=location_id)
        if item.location_id != location.pk:
            return JsonResponse({
                "ok": False,
                "error": f"{barcode} is at {item.location.name}, not {location.name} — wrong scanning location selected?",
            })

    return JsonResponse({
        "ok": True,
        "barcode": item.barcode,
        "product_name": item.product.name,
        "unit_price": str(item.product.selling_price or "0"),
    })


@login_required
@require_POST
def invoice_create(request):
    """
    "+ New invoice" — redesigned 27 Aug 2026 around how items actually
    get added on the floor (see module docstring): a barcode is scanned
    via item_lookup, which resolves it and pulls its price, and only a
    resolved barcode ever reaches this endpoint as a line. This view
    re-validates everything server-side regardless — the same
    eligibility/duplicate checks as item_lookup, run again here, because
    the client-side scan step is a UX convenience, not the source of
    truth.

    Kept as plain POST + redirect rather than a JSON API + client-side
    render, consistent with the rest of this app (no SPA layer exists
    here). Validation failures go through django.contrib.messages and
    send the user back to the list — they re-open "+ New invoice" and
    re-scan, rather than the form re-appearing pre-filled. A real gap
    versus pj-accounting's in-place error display; acceptable for this
    pass, worth revisiting once usage shows whether it matters.
    """
    reseller = get_object_or_404(Reseller, pk=request.POST.get("reseller"))
    is_reserve = request.POST.get("is_reserve") == "on"

    display_slot = None
    slot_id = request.POST.get("display_slot")

    barcodes = request.POST.getlist("item_barcode")
    unit_prices = request.POST.getlist("unit_price")
    discounts = request.POST.getlist("discount_percent")
    commission_types = request.POST.getlist("commission_type")
    commission_rates = request.POST.getlist("commission_rate")

    def _at(values, i, default=""):
        return values[i] if i < len(values) else default

    rows = []
    errors = []
    seen_barcodes = set()

    if slot_id:
        display_slot = get_object_or_404(DisplaySlot, pk=slot_id)
        active = display_slot.allotments.filter(released_at__isnull=True).select_related("reseller").first()
        if active and active.reseller_id != reseller.pk:
            errors.append(f"{display_slot.name} is currently allotted to {active.reseller.name}.")

    for i, raw_barcode in enumerate(barcodes):
        barcode = raw_barcode.strip()
        if not barcode:
            continue
        if barcode in seen_barcodes:
            errors.append(f"{barcode} was scanned twice on this invoice.")
            continue
        seen_barcodes.add(barcode)

        try:
            item = ProductItem.objects.select_related("product").get(barcode=barcode)
        except ProductItem.DoesNotExist:
            errors.append(f"No item with barcode {barcode!r}.")
            continue
        if item.status not in (StockStatus.PENDING, StockStatus.RESERVED):
            errors.append(f"{barcode} is {item.status}, not eligible for assignment.")
            continue

        try:
            unit_price = Decimal(_at(unit_prices, i) or "0")
            discount_percent = Decimal(_at(discounts, i) or "0")
            raw_rate = _at(commission_rates, i)
            commission_rate = Decimal(raw_rate) if raw_rate else None
        except InvalidOperation:
            errors.append(f"{barcode}: price, discount, or commission rate isn't a valid number.")
            continue

        if unit_price <= 0:
            errors.append(f"{barcode}: unit price must be greater than 0.")
            continue

        rows.append({
            "item": item,
            "unit_price": unit_price,
            "discount_percent": discount_percent,
            "commission_type": _at(commission_types, i),
            "commission_rate": commission_rate,
        })

    if not rows and not errors:
        errors.append("Scan at least one item onto this invoice before saving.")

    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect("assignment:invoice_list")

    with transaction.atomic():
        master = AssignmentMaster.objects.create(
            reseller=reseller, is_reserve=is_reserve, display_slot=display_slot, created_by=request.user,
        )
        for row in rows:
            line = master.add_line(row["item"], unit_price=row["unit_price"], actor=request.user)
            line.discount_percent = row["discount_percent"]
            line.commission_type = row["commission_type"]
            line.commission_rate = row["commission_rate"]
            line.save()
        if display_slot and not display_slot.allotments.filter(released_at__isnull=True, reseller=reseller).exists():
            DisplaySlotAllotment.objects.create(slot=display_slot, reseller=reseller)

    messages.success(request, f"Invoice {master.invoice_number} created with {len(rows)} item(s).")
    return redirect("assignment:invoice_detail", pk=master.pk)


@login_required
@require_POST
def invoice_stamp(request, pk):
    """Mark an invoice COMPLETE — thin wrapper around AssignmentMaster.stamp_invoice()."""
    master = get_object_or_404(AssignmentMaster, pk=pk)
    master.stamp_invoice(actor=request.user)
    messages.success(request, f"Invoice {master.invoice_number} marked complete.")
    return redirect("assignment:invoice_detail", pk=master.pk)
