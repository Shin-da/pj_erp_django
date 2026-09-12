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
from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.access import require_perm
from apps.core.models import LegacyDocument
from apps.inventory.models import ProductItem, StockStatus
from apps.locations.models import Location
from apps.payments.models import ResellerPayment

from .invoice_pdf import render_invoice_html, render_invoice_pdf
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

    money = DecimalField(max_digits=14, decimal_places=2)
    # The SQL form of AssignmentLine.calculate_line_total(). The list used
    # to sum unit_price and call itself "discount-blind on purpose" — but a
    # discounted invoice then showed at full price in the list and at its
    # real price in the detail beside it, which reads as a bug rather than
    # a shortcut. Same expression as the dashboard uses.
    net_line = ExpressionWrapper(
        F("lines__unit_price")
        * (Value(Decimal("100")) - F("lines__discount_percent"))
        / Value(Decimal("100")),
        output_field=money,
    )
    paid_sq = Subquery(
        ResellerPayment.objects.filter(assignment_id=OuterRef("pk"))
        .values("assignment_id")
        .annotate(t=Sum("amount"))
        .values("t")[:1],
        output_field=money,
    )

    invoices = (
        AssignmentMaster.objects.select_related("reseller")
        .annotate(
            line_count=Count("lines", distinct=True),
            list_amount=Sum(net_line),
            paid_amount=Coalesce(paid_sq, Value(Decimal("0.00"), output_field=money)),
        )
        .order_by("-created_at")
    )
    if q:
        invoices = invoices.filter(Q(invoice_number__icontains=q) | Q(reseller__name__icontains=q))
    if status:
        invoices = invoices.filter(invoice_status=status)

    paginator = Paginator(invoices, 30)
    page_obj = paginator.get_page(request.GET.get("page"))

    # One colour vocabulary across the app, applied here to what actually
    # matters about an invoice: whether money is owed. Colouring purely by
    # invoice_status made the list a wall of identical green "Invoiced"
    # pills whether a row was settled or six figures outstanding.
    #
    #   ok      settled / nothing to do
    #   info    out on purpose, an active commitment
    #   warn    needs attention, time-bound
    #   danger  void, broken
    #
    # Every state also carries a WORD, never colour alone — the page is
    # printed in greyscale and read by colour-blind operators.
    for inv in page_obj:
        billed = inv.list_amount or Decimal("0")
        paid = inv.paid_amount or Decimal("0")
        inv.balance = billed - paid
        if inv.invoice_status == InvoiceStatus.CANCELLED:
            inv.pay_state, inv.pay_label, inv.pay_tone = "VOID", "Cancelled", "danger"
        elif inv.invoice_status == InvoiceStatus.DRAFT:
            inv.pay_state, inv.pay_label, inv.pay_tone = "DRAFT", "Draft", "warn"
        elif inv.balance <= 0 and billed > 0:
            inv.pay_state, inv.pay_label, inv.pay_tone = "PAID", "Paid", "ok"
        elif paid > 0:
            inv.pay_state, inv.pay_label, inv.pay_tone = "PARTIAL", "Part paid", "warn"
        else:
            inv.pay_state, inv.pay_label, inv.pay_tone = "UNPAID", "Unpaid", "info"

    selected = None
    if pk:
        selected = get_object_or_404(
            AssignmentMaster.objects.select_related("reseller", "display_slot", "created_by"), pk=pk
        )
        selected.line_list = list(
            selected.lines.select_related(
                "item", "item__product", "item__product__category", "item__product__currency", "item__location"
            ).order_by("id")
        )
        selected.amount_total = sum((line.calculate_line_total() for line in selected.line_list), Decimal("0"))
        selected.commission_total = sum((line.commission_value for line in selected.line_list), Decimal("0"))

        # Hide columns that are empty for THIS invoice. Most invoices carry
        # no discount and no commission, and two columns of "—" across
        # eleven rows push the numbers that matter off to the side.
        selected.has_discount = any(line.discount_percent for line in selected.line_list)
        selected.has_commission = any(line.commission_type for line in selected.line_list)

        # Where each piece actually is now. An invoice is a record of what
        # went out; the operator's real question is what came back. Without
        # this the page cannot distinguish "eleven pieces with the reseller"
        # from "eleven pieces already returned" — which is exactly why a
        # cancelled invoice used to read like a live one.
        status_tally = {}
        for line in selected.line_list:
            status_tally[line.item.status] = status_tally.get(line.item.status, 0) + 1
        selected.status_tally = [
            {"status": s, "label": StockStatus(s).label, "n": n}
            for s, n in sorted(status_tally.items(), key=lambda kv: -kv[1])
        ]
        selected.still_out = status_tally.get(StockStatus.ASSIGNED, 0) + status_tally.get(
            StockStatus.RESERVED, 0
        )

        # Money actually collected against this invoice.
        payments = list(
            ResellerPayment.objects.filter(assignment=selected)
            .select_related("recorded_by")
            .order_by("-paid_on", "-id")
        )
        # NOT `selected.payments` — ResellerPayment declares
        # related_name="payments", so that attribute is the reverse
        # manager and assigning to it raises.
        selected.payment_list = payments
        selected.paid_total = sum((p.amount for p in payments), Decimal("0"))
        selected.balance = selected.amount_total - selected.paid_total
        # A cancelled invoice is not "outstanding" — nothing is owed on a
        # document that no longer stands. Say that instead of showing a
        # balance someone might try to collect.
        selected.is_void = selected.invoice_status == InvoiceStatus.CANCELLED

        # The PDF the legacy system generated for this invoice, if this
        # row predates the rebuild and the file was migrated across. It is
        # the document the customer was actually handed; the screen above
        # is today's data, and the two can legitimately disagree if the
        # record was corrected afterwards.
        selected.legacy_docs = list(LegacyDocument.for_object(selected))

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


@require_perm("assignment.can_create_invoice")
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


@require_perm("assignment.can_create_invoice")
@require_POST
def invoice_create(request):
    """
    "+ New invoice" — redesigned 27 Aug 2026 around how items actually
    get added on the floor (see module docstring). Shared create logic
    lives in ``assignment.services.create_invoice`` (also used by the API).
    """
    reseller = get_object_or_404(Reseller, pk=request.POST.get("reseller"))
    is_reserve = request.POST.get("is_reserve") == "on"

    display_slot = None
    slot_id = request.POST.get("display_slot")
    if slot_id:
        display_slot = get_object_or_404(DisplaySlot, pk=slot_id)

    barcodes = request.POST.getlist("item_barcode")
    unit_prices = request.POST.getlist("unit_price")
    discounts = request.POST.getlist("discount_percent")
    commission_types = request.POST.getlist("commission_type")
    commission_rates = request.POST.getlist("commission_rate")

    def _at(values, i, default=""):
        return values[i] if i < len(values) else default

    lines = []
    for i, raw_barcode in enumerate(barcodes):
        barcode = raw_barcode.strip()
        if not barcode:
            continue
        lines.append(
            {
                "barcode": barcode,
                "unit_price": _at(unit_prices, i) or "0",
                "discount_percent": _at(discounts, i) or "0",
                "commission_type": _at(commission_types, i),
                "commission_rate": _at(commission_rates, i) or None,
            }
        )

    from django.core.exceptions import ValidationError
    from .services import create_invoice

    try:
        master = create_invoice(
            reseller=reseller,
            lines=lines,
            actor=request.user,
            is_reserve=is_reserve,
            display_slot=display_slot,
        )
    except ValidationError as exc:
        detail = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
        messages.error(request, detail)
        return redirect("assignment:invoice_list")

    messages.success(
        request,
        f"Invoice {master.invoice_number} created with {master.lines.count()} item(s).",
    )
    return redirect("assignment:invoice_detail", pk=master.pk)


@require_perm("assignment.can_stamp_invoice")
@require_POST
def invoice_stamp(request, pk):
    """Mark an invoice COMPLETE — thin wrapper around AssignmentMaster.stamp_invoice()."""
    master = get_object_or_404(AssignmentMaster, pk=pk)
    master.stamp_invoice(actor=request.user)
    messages.success(request, f"Invoice {master.invoice_number} marked complete.")
    return redirect("assignment:invoice_detail", pk=master.pk)


@login_required
def invoice_pdf(request, pk):
    """
    The generated invoice, as a PDF.

    Unlike the legacy `ResellerPaymentInvoice.aspx`, asking for the PDF
    does NOT stamp the invoice complete, does not delete payment rows,
    and does not write anything at all — it is a pure read. Marking an
    invoice complete is its own explicit action.

    `?download=1` forces a save dialog; without it the browser displays
    it inline, which is what someone clicking "PDF" on the invoice page
    expects.
    """
    master = get_object_or_404(
        AssignmentMaster.objects.select_related("reseller", "reseller_location"), pk=pk
    )
    try:
        pdf_bytes = render_invoice_pdf(master, base_url=request.build_absolute_uri("/"))
    except RuntimeError as exc:
        messages.error(request, str(exc))
        return redirect("assignment:invoice_detail", pk=master.pk)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{master.invoice_number}.pdf"'
    return response


@login_required
def invoice_pdf_preview(request, pk):
    """
    The same layout rendered as plain HTML.

    Exists so the invoice design can be worked on without a PDF engine
    installed, and so a print-to-PDF from the browser stays available if
    WeasyPrint won't build on a given machine.
    """
    master = get_object_or_404(
        AssignmentMaster.objects.select_related("reseller", "reseller_location"), pk=pk
    )
    return HttpResponse(render_invoice_html(master))
