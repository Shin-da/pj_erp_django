"""
Product master — the "what do we actually own" pages.

Three levels, each its own real URL (so anything here is linkable,
bookmarkable and reachable from the global search bar):

  product_list    — one row per DESIGN (catalogue.ProductMaster), with live
                    piece counts rolled up from inventory.ProductItem.
  product_detail  — one design's full spec sheet plus the table of every
                    physical barcode cut from it, and where each one is.
  item_detail     — one physical piece (inventory.ProductItem): its status,
                    its location, and its real audit history.

Deliberately read-only for now. Editing a design or an item still happens
in Django admin — these pages exist so anyone can *find* and *inspect*
stock without needing admin access or knowing which location to look in
first, which is the thing the legacy system genuinely could not do (its
only stock views were location-scoped grids).

Counts are annotated in one query per page rather than looped, so a
product with 400 pieces costs the same as one with 4.
"""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from apps.catalogue.labels import subcategory_label
from apps.catalogue.models import Category, ProductMaster, Supplier
from apps.core.models import AuditLogEntry
from apps.inventory.models import ProductItem, StockStatus
from apps.locations.models import Location


def _stock_annotations():
    """Piece counts per design, by status. Shared by list and detail."""
    return {
        "item_count": Count("items", distinct=True),
        "available_count": Count("items", filter=Q(items__status=StockStatus.PENDING), distinct=True),
        "assigned_count": Count("items", filter=Q(items__status=StockStatus.ASSIGNED), distinct=True),
        "reserved_count": Count("items", filter=Q(items__status=StockStatus.RESERVED), distinct=True),
        "sold_count": Count("items", filter=Q(items__status=StockStatus.SOLD), distinct=True),
        "in_transit_count": Count("items", filter=Q(items__status=StockStatus.IN_TRANSIT), distinct=True),
    }


@login_required
def product_list(request):
    """
    The product master list. Search matches the design's own fields AND the
    barcodes cut from it, so pasting a barcode in here finds its design —
    the same string works in the nav search bar and lands you deeper.
    """
    products = (
        ProductMaster.objects.select_related("category", "currency", "metal", "purity", "supplier")
        .prefetch_related("images")
        .annotate(**_stock_annotations())
    )

    q = request.GET.get("q", "").strip()
    if q:
        products = products.filter(
            Q(name__icontains=q)
            | Q(reference_id__icontains=q)
            | Q(subcategory__icontains=q)
            | Q(items__barcode__icontains=q)
        ).distinct()

    category = request.GET.get("category", "").strip()
    if category:
        products = products.filter(category__code=category)

    supplier = request.GET.get("supplier", "").strip()
    if supplier:
        products = products.filter(supplier_id=supplier)

    subcategory = request.GET.get("subcategory", "").strip()
    if subcategory:
        products = products.filter(subcategory=subcategory)

    # "stock" filter works on the annotated rollups, not on a stored field —
    # there is no denormalised stock column to drift out of sync here.
    stock = request.GET.get("stock", "").strip()
    if stock == "AVAILABLE":
        products = products.filter(available_count__gt=0)
    elif stock == "SOLD":
        products = products.filter(sold_count__gt=0)
    elif stock == "ASSIGNED":
        products = products.filter(assigned_count__gt=0)
    elif stock == "OUT":
        products = products.filter(available_count=0)
    elif stock == "NONE":
        products = products.filter(item_count=0)

    sort = request.GET.get("sort", "name")
    sort_map = {
        "name": "name",
        "-name": "-name",
        "stock": "item_count",
        "-stock": "-item_count",
        "available": "available_count",
        "-available": "-available_count",
        "price": "selling_price",
        "-price": "-selling_price",
    }
    products = products.order_by(sort_map.get(sort, "name"))

    paginator = Paginator(products, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    subcategory_choices = [
        (code, subcategory_label(code))
        for code in (
            ProductMaster.objects.exclude(subcategory="")
            .values_list("subcategory", flat=True)
            .distinct()
            .order_by("subcategory")
        )
    ]

    return render(request, "catalogue/product_list.html", {
        "page_obj": page_obj,
        "q": q,
        "category": category,
        "supplier": supplier,
        "subcategory": subcategory,
        "stock": stock,
        "sort": sort,
        "categories": Category.objects.order_by("name"),
        "suppliers": Supplier.objects.order_by("name"),
        "subcategory_choices": subcategory_choices,
        "total_count": paginator.count,
    })


@login_required
def product_detail(request, pk):
    """One design: its spec sheet, its stock rollup, and every piece of it."""
    product = get_object_or_404(
        ProductMaster.objects.select_related("category", "currency", "metal", "purity", "supplier")
        .annotate(**_stock_annotations()),
        pk=pk,
    )

    items = (
        ProductItem.objects.filter(product=product)
        .select_related("location")
        .order_by("barcode")
    )

    status = request.GET.get("status", "").strip()
    if status:
        items = items.filter(status=status)

    location = request.GET.get("location", "").strip()
    if location:
        items = items.filter(location__code=location)

    paginator = Paginator(items, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Which locations this design is actually sitting in — the question
    # "where are our Solid Gold Bands?" used to need one query per branch.
    by_location = (
        Location.objects.filter(items__product=product)
        .annotate(
            n=Count("items", filter=Q(items__product=product), distinct=True),
            n_available=Count(
                "items",
                filter=Q(items__product=product, items__status=StockStatus.PENDING),
                distinct=True,
            ),
        )
        .order_by("-n")
    )

    return render(request, "catalogue/product_detail.html", {
        "product": product,
        "page_obj": page_obj,
        "by_location": by_location,
        "status": status,
        "location": location,
        "status_choices": StockStatus.choices,
        "locations": Location.objects.order_by("name"),
    })


@login_required
def item_detail(request, barcode):
    """
    One physical piece. This is what a barcode scan in the nav search bar
    lands on, so it's built to answer the scanning operator's questions
    first: what is it, where does the system think it is, what state is it
    in, and what has happened to it.
    """
    item = get_object_or_404(
        ProductItem.objects.select_related(
            "product", "product__category", "product__currency",
            "product__metal", "product__purity", "product__supplier",
            "location",
        ),
        barcode=barcode,
    )

    history = AuditLogEntry.objects.filter(
        model_label="inventory.productitem", object_id=str(item.pk)
    ).select_related("actor")[:50]

    siblings = (
        ProductItem.objects.filter(product=item.product)
        .exclude(pk=item.pk)
        .select_related("location")
        .order_by("barcode")[:12]
    )
    sibling_total = ProductItem.objects.filter(product=item.product).exclude(pk=item.pk).count()

    return render(request, "catalogue/item_detail.html", {
        "item": item,
        "history": history,
        "siblings": siblings,
        "sibling_total": sibling_total,
    })
