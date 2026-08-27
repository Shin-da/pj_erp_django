"""
Global search — the nav bar's search box.

Two entry points:

  search_suggest  — JSON, called live (debounced) while typing. Returns a
                    small, grouped set of matches for the dropdown.
  search          — the full results page you land on when you press Enter
                    without an exact barcode match.

Design notes:

  - An EXACT barcode match (case-insensitive) is special-cased in both
    places: the dropdown pins it to the top, and pressing Enter on it
    redirects straight to that item's page. This is the scanning-gun path
    — an operator scans into the search box and lands on the piece, no
    clicks. A physical scanner types the barcode then sends Enter, which
    is exactly this flow, so it works with the hardware you already have.
  - Searches are capped and ordered per group rather than UNION-ed into
    one ranked list. Ranking across heterogeneous models needs either a
    real search index or a scoring hack that lies; grouping is honest
    about what matched and costs three cheap indexed queries.
  - `barcode` and `reference_id` are both db_index'd, so the icontains
    scans here stay acceptable at the current row counts. If/when the
    item table grows past comfort, this is the one place to swap in
    Postgres full-text or trigram indexes — nothing else needs to change.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render

from apps.assignment.models import Reseller, ResellerGroup
from apps.catalogue.models import ProductMaster
from apps.inventory.models import ProductItem, StockStatus
from apps.locations.models import Location

SUGGEST_LIMIT = 6

STATUS_LABELS = {
    StockStatus.PENDING: "Available",
    StockStatus.ASSIGNED: "Assigned",
    StockStatus.RESERVED: "Reserved",
    StockStatus.SOLD: "Sold",
    StockStatus.IN_TRANSIT: "In transit",
}


def _exact_item(q):
    """The scan-and-go case: one barcode, matched exactly."""
    if not q:
        return None
    return ProductItem.objects.filter(barcode__iexact=q).select_related("product", "location").first()


def _item_matches(q, limit):
    return (
        ProductItem.objects.filter(barcode__icontains=q)
        .select_related("product", "location")
        .order_by("barcode")[:limit]
    )


def _product_matches(q, limit):
    return (
        ProductMaster.objects.filter(
            Q(name__icontains=q) | Q(reference_id__icontains=q) | Q(subcategory__icontains=q)
        )
        .select_related("category", "currency")
        .annotate(
            item_count=Count("items", distinct=True),
            available_count=Count("items", filter=Q(items__status=StockStatus.PENDING), distinct=True),
        )
        .order_by("name")[:limit]
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


@login_required
def search_suggest(request):
    """JSON for the nav dropdown. Kept small on purpose — this fires per keystroke."""
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"q": q, "exact": None, "groups": []})

    exact = _exact_item(q)
    exact_payload = None
    if exact:
        exact_payload = {
            "barcode": exact.barcode,
            "product": exact.product.name,
            "location": exact.location.code,
            "status": STATUS_LABELS.get(exact.status, exact.get_status_display()),
            "url": f"/products/item/{exact.barcode}/",
        }

    groups = []

    items = [
        {
            "label": i.barcode,
            "sub": f"{i.product.name} · {i.location.code} · {STATUS_LABELS.get(i.status, i.status)}",
            "url": f"/products/item/{i.barcode}/",
        }
        for i in _item_matches(q, SUGGEST_LIMIT)
        if not (exact and i.pk == exact.pk)
    ]
    if items:
        groups.append({"title": "Barcodes", "icon": "fa-barcode", "results": items})

    products = [
        {
            "label": p.name,
            "sub": (f"{p.reference_id} · " if p.reference_id else "")
                   + f"{p.category.name} · {p.item_count} pc, {p.available_count} available",
            "url": f"/products/{p.pk}/",
        }
        for p in _product_matches(q, SUGGEST_LIMIT)
    ]
    if products:
        groups.append({"title": "Products", "icon": "fa-gem", "results": products})

    clients, reseller_groups = _reseller_matches(q, SUGGEST_LIMIT)
    people = [
        {
            "label": c.name,
            "sub": (c.group.name if c.group else "Ungrouped")
                   + (f" · {c.reference_code}" if c.reference_code else ""),
            "url": f"/resellers/client/{c.pk}/",
        }
        for c in clients
    ] + [
        {
            "label": f"{g.name} ({g.code})",
            "sub": f"Group · {g.client_count} client{'' if g.client_count == 1 else 's'}",
            "url": f"/resellers/group/{g.pk}/",
        }
        for g in reseller_groups
    ]
    if people:
        groups.append({"title": "Resellers", "icon": "fa-users", "results": people})

    locations = [
        {
            "label": f"{loc.name} ({loc.code})",
            "sub": f"{loc.item_count} item{'' if loc.item_count == 1 else 's'}",
            "url": f"/inventory/locations/{loc.code}/",
        }
        for loc in _location_matches(q, SUGGEST_LIMIT)
    ]
    if locations:
        groups.append({"title": "Locations", "icon": "fa-location-dot", "results": locations})

    return JsonResponse({"q": q, "exact": exact_payload, "groups": groups})


@login_required
def search(request):
    """
    Full results page. If the query is an exact barcode, skip the page
    entirely and go straight to the piece — same behaviour as the dropdown,
    so the two never disagree about what Enter does.
    """
    q = request.GET.get("q", "").strip()

    if q:
        exact = _exact_item(q)
        if exact:
            return redirect("catalogue:item_detail", barcode=exact.barcode)

    items = _item_matches(q, 50) if q else []
    products = _product_matches(q, 50) if q else []
    locations = _location_matches(q, 25) if q else []
    clients, reseller_groups = _reseller_matches(q, 25) if q else ([], [])

    return render(request, "core/search.html", {
        "q": q,
        "items": items,
        "products": products,
        "locations": locations,
        "clients": clients,
        "reseller_groups": reseller_groups,
        "total": len(items) + len(products) + len(locations) + len(clients) + len(reseller_groups),
    })
