"""
Global search — the nav bar's search box.

Two entry points:

  search_suggest  — JSON, called live (debounced) while typing. Returns a
                    small, grouped set of matches for the dropdown.
  search          — the full results page you land on when you press Enter
                    without an exact barcode/EPC match.

Design notes:

  - An EXACT barcode or RFID EPC match (case-insensitive) is special-cased
    in both places: the dropdown pins it to the top, and pressing Enter
    redirects straight to that item's page. This is the scanning-gun path
    — an operator scans into the search box and lands on the piece, no
    clicks. A physical scanner types the barcode then sends Enter, which
    is exactly this flow, so it works with the hardware you already have.
  - Searches are capped and ordered per group rather than UNION-ed into
    one ranked list. Ranking across heterogeneous models needs either a
    real search index or a scoring hack that lies; grouping is honest
    about what matched and costs a handful of cheap indexed queries.
  - `barcode` and `reference_id` are both db_index'd, so the icontains
    scans here stay acceptable at the current row counts. If/when the
    item table grows past comfort, this is the one place to swap in
    Postgres full-text or trigram indexes — nothing else needs to change.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.assignment.models import AssignmentMaster, InvoiceStatus, Reseller, ResellerGroup
from apps.catalogue.models import ProductMaster
from apps.inventory.models import ProductItem, StockStatus
from apps.locations.models import Location

SUGGEST_LIMIT = 6
PAGE_LIMIT_ITEMS = 50
PAGE_LIMIT_PRODUCTS = 50
PAGE_LIMIT_INVOICES = 25
PAGE_LIMIT_OTHER = 25

STATUS_LABELS = {
    StockStatus.PENDING: "Available",
    StockStatus.ASSIGNED: "Assigned",
    StockStatus.RESERVED: "Reserved",
    StockStatus.SOLD: "Sold",
    StockStatus.IN_TRANSIT: "In transit",
}

INVOICE_STATUS_LABELS = {
    InvoiceStatus.DRAFT: "Draft",
    InvoiceStatus.COMPLETE: "Complete",
    InvoiceStatus.CANCELLED: "Cancelled",
}


def _exact_item(q):
    """The scan-and-go case: one barcode or RFID EPC, matched exactly."""
    if not q:
        return None
    qs = ProductItem.objects.select_related("product", "location")
    item = qs.filter(barcode__iexact=q).first()
    if item:
        return item
    return qs.filter(rfid_epc__iexact=q).exclude(rfid_epc="").first()


def _item_matches(q, limit):
    return (
        ProductItem.objects.filter(Q(barcode__icontains=q) | Q(rfid_epc__icontains=q))
        .select_related("product", "location")
        .order_by("barcode")[:limit]
    )


def _product_matches(q, limit):
    # Same surface as the product list: design fields + piece barcodes, so
    # pasting a barcode finds the product design as well as the piece.
    return (
        ProductMaster.objects.filter(
            Q(name__icontains=q)
            | Q(reference_id__icontains=q)
            | Q(subcategory__icontains=q)
            | Q(items__barcode__icontains=q)
        )
        .distinct()
        .select_related("category", "currency")
        .annotate(
            item_count=Count("items", distinct=True),
            available_count=Count("items", filter=Q(items__status=StockStatus.PENDING), distinct=True),
        )
        .order_by("reference_id", "name")[:limit]
    )


def _location_matches(q, limit):
    return (
        Location.objects.filter(Q(name__icontains=q) | Q(code__icontains=q))
        .annotate(item_count=Count("items", distinct=True))
        .order_by("name")[:limit]
    )


def _reseller_matches(q, limit):
    """Clients and the groups they sit under, in one list — staff search by
    a person's name without knowing or caring which group they're filed in."""
    clients = (
        Reseller.objects.filter(Q(name__icontains=q) | Q(reference_code__icontains=q))
        .select_related("group")
        .order_by("name")[:limit]
    )
    groups = (
        ResellerGroup.objects.filter(Q(name__icontains=q) | Q(code__icontains=q))
        .annotate(client_count=Count("clients", distinct=True))
        .order_by("name")[:limit]
    )
    return clients, groups


def _invoice_matches(q, limit):
    return (
        AssignmentMaster.objects.filter(
            Q(invoice_number__icontains=q) | Q(reseller__name__icontains=q)
        )
        .select_related("reseller")
        .annotate(line_count=Count("lines", distinct=True))
        .order_by("-created_at")[:limit]
    )


def _item_payload(item):
    return {
        "barcode": item.barcode,
        "product": item.product.name,
        "location": item.location.code,
        "status": STATUS_LABELS.get(item.status, item.get_status_display()),
        "url": reverse("catalogue:item_detail", kwargs={"barcode": item.barcode}),
    }


@login_required
def search_suggest(request):
    """JSON for the nav dropdown. Kept small on purpose — this fires per keystroke."""
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"q": q, "exact": None, "groups": []})

    exact = _exact_item(q)
    exact_payload = None
    if exact:
        exact_payload = _item_payload(exact)

    groups = []

    items = [
        {
            "label": i.barcode,
            "sub": f"{i.product.name} · {i.location.code} · {STATUS_LABELS.get(i.status, i.status)}",
            "url": reverse("catalogue:item_detail", kwargs={"barcode": i.barcode}),
        }
        for i in _item_matches(q, SUGGEST_LIMIT)
        if not (exact and i.pk == exact.pk)
    ]
    if items:
        groups.append({"title": "Barcodes", "icon": "fa-barcode", "results": items})

    products = [
        {
            "label": p.reference_id or p.name,
            "sub": (
                (f"{p.name} · " if p.reference_id and p.name else "")
                + f"{p.category.name} · {p.item_count} pc, {p.available_count} available"
            ),
            "url": reverse("catalogue:product_detail", kwargs={"pk": p.pk}),
        }
        for p in _product_matches(q, SUGGEST_LIMIT)
    ]
    if products:
        groups.append({"title": "Products", "icon": "fa-gem", "results": products})

    invoices = [
        {
            "label": inv.invoice_number or f"#{inv.pk}",
            "sub": (
                f"{inv.reseller.name} · "
                f"{INVOICE_STATUS_LABELS.get(inv.invoice_status, inv.invoice_status)}"
                f" · {inv.line_count} line{'s' if inv.line_count != 1 else ''}"
            ),
            "url": reverse("assignment:invoice_detail", kwargs={"pk": inv.pk}),
        }
        for inv in _invoice_matches(q, SUGGEST_LIMIT)
    ]
    if invoices:
        groups.append({"title": "Invoices", "icon": "fa-file-invoice", "results": invoices})

    clients, reseller_groups = _reseller_matches(q, SUGGEST_LIMIT)
    people = [
        {
            "label": c.name,
            "sub": (c.group.name if c.group else "Ungrouped")
                   + (f" · {c.reference_code}" if c.reference_code else ""),
            "url": reverse("assignment:client_detail", kwargs={"pk": c.pk}),
        }
        for c in clients
    ] + [
        {
            "label": f"{g.name} ({g.code})",
            "sub": f"Group · {g.client_count} client{'' if g.client_count == 1 else 's'}",
            "url": reverse("assignment:group_detail", kwargs={"pk": g.pk}),
        }
        for g in reseller_groups
    ]
    if people:
        groups.append({"title": "Resellers", "icon": "fa-users", "results": people})

    locations = [
        {
            "label": f"{loc.name} ({loc.code})",
            "sub": f"{loc.item_count} item{'' if loc.item_count == 1 else 's'}",
            "url": reverse("inventory:location_detail", kwargs={"code": loc.code}),
        }
        for loc in _location_matches(q, SUGGEST_LIMIT)
    ]
    if locations:
        groups.append({"title": "Locations", "icon": "fa-location-dot", "results": locations})

    return JsonResponse({"q": q, "exact": exact_payload, "groups": groups})


@login_required
def search(request):
    """
    Full results page. If the query is an exact barcode or RFID EPC, skip
    the page entirely and go straight to the piece — same behaviour as the
    dropdown, so the two never disagree about what Enter does.
    """
    q = request.GET.get("q", "").strip()

    if q:
        exact = _exact_item(q)
        if exact:
            return redirect("catalogue:item_detail", barcode=exact.barcode)

    items = list(_item_matches(q, PAGE_LIMIT_ITEMS)) if q else []
    products = list(_product_matches(q, PAGE_LIMIT_PRODUCTS)) if q else []
    invoices = list(_invoice_matches(q, PAGE_LIMIT_INVOICES)) if q else []
    locations = list(_location_matches(q, PAGE_LIMIT_OTHER)) if q else []
    clients, reseller_groups = _reseller_matches(q, PAGE_LIMIT_OTHER) if q else ([], [])
    clients = list(clients)
    reseller_groups = list(reseller_groups)

    counts = {
        "items": len(items),
        "products": len(products),
        "invoices": len(invoices),
        "resellers": len(clients) + len(reseller_groups),
        "locations": len(locations),
    }
    total = sum(counts.values())

    return render(request, "core/search.html", {
        "q": q,
        "items": items,
        "products": products,
        "invoices": invoices,
        "locations": locations,
        "clients": clients,
        "reseller_groups": reseller_groups,
        "counts": counts,
        "total": total,
    })
