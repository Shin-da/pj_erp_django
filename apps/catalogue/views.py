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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import urlencode

from apps.accounts.access import is_developer
from apps.catalogue.datafile import sync_datafile
from apps.catalogue.intake import (
    IntakeRow,
    apply_rows,
    default_location,
    parse_jewellery_workbook,
)
from apps.catalogue.labels import subcategory_label
from apps.catalogue.models import Category, ProductMaster, Supplier
from apps.core.models import AuditLogEntry
from apps.core.search import _exact_item
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


def _product_list_query(request, **overrides):
    """Preserve list filters across pagination / view toggles."""
    params = {
        "q": request.GET.get("q", "").strip(),
        "category": request.GET.get("category", "").strip(),
        "supplier": request.GET.get("supplier", "").strip(),
        "subcategory": request.GET.get("subcategory", "").strip(),
        "stock": request.GET.get("stock", "").strip(),
        "sort": request.GET.get("sort", "reference").strip() or "reference",
        "view": request.GET.get("view", "grid").strip() or "grid",
    }
    params.update(overrides)
    cleaned = {
        k: v for k, v in params.items()
        if v not in ("", None)
        and not (k == "sort" and v == "reference")
        and not (k == "view" and v == "grid")
    }
    return urlencode(cleaned)


@login_required
def product_list(request):
    """
    The product master list. Search matches the design's own fields AND the
    barcodes cut from it. An exact PJ/barcode (or RFID EPC) redirects to the
    piece page — same scan-and-go path as the nav search bar.
    """
    q = request.GET.get("q", "").strip()
    if q:
        exact = _exact_item(q)
        if exact:
            return redirect("catalogue:item_detail", barcode=exact.barcode)

    sample_barcode = Subquery(
        ProductItem.objects.filter(product_id=OuterRef("pk"))
        .order_by("barcode")
        .values("barcode")[:1]
    )
    products = (
        ProductMaster.objects.select_related("category", "currency", "metal", "purity", "supplier")
        .prefetch_related("images")
        .annotate(**_stock_annotations(), sample_barcode=sample_barcode)
    )

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

    # Summary chips reflect search/category/supplier filters, but ignore the
    # stock chip itself — otherwise clicking "With available" collapses the
    # other counts to zero and the strip stops being useful for switching.
    stats = products.aggregate(
        design_total=Count("pk"),
        with_available=Count("pk", filter=Q(available_count__gt=0)),
        out_of_stock=Count("pk", filter=Q(item_count__gt=0, available_count=0)),
        no_pieces=Count("pk", filter=Q(item_count=0)),
        piece_total=Sum("item_count"),
        available_total=Sum("available_count"),
    )

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
        products = products.filter(available_count=0, item_count__gt=0)
    elif stock == "NONE":
        products = products.filter(item_count=0)

    # Default by reference_id: many legacy designs share a style name
    # (e.g. ANICH1) while the reference is what actually distinguishes them.
    sort = request.GET.get("sort", "reference").strip() or "reference"
    sort_map = {
        "reference": ("reference_id", "name"),
        "-reference": ("-reference_id", "-name"),
        "name": ("name", "reference_id"),
        "-name": ("-name", "-reference_id"),
        "stock": ("item_count", "reference_id"),
        "-stock": ("-item_count", "reference_id"),
        "available": ("available_count", "reference_id"),
        "-available": ("-available_count", "reference_id"),
        "price": ("selling_price", "reference_id"),
        "-price": ("-selling_price", "reference_id"),
    }
    products = products.order_by(*sort_map.get(sort, sort_map["reference"]))

    view = request.GET.get("view", "grid").strip()
    if view not in ("grid", "list"):
        view = "grid"
    per_page = 24 if view == "grid" else 50

    paginator = Paginator(products, per_page)
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

    category_obj = Category.objects.filter(code=category).first() if category else None
    supplier_obj = Supplier.objects.filter(pk=supplier).first() if supplier else None
    stock_labels = {
        "AVAILABLE": "Has available stock",
        "SOLD": "Has sold pieces",
        "ASSIGNED": "Has assigned pieces",
        "OUT": "Nothing available",
        "NONE": "No pieces at all",
    }

    return render(request, "catalogue/product_list.html", {
        "page_obj": page_obj,
        "q": q,
        "category": category,
        "supplier": supplier,
        "subcategory": subcategory,
        "stock": stock,
        "sort": sort,
        "view": view,
        "categories": Category.objects.order_by("name"),
        "suppliers": Supplier.objects.order_by("name"),
        "subcategory_choices": subcategory_choices,
        "total_count": paginator.count,
        "stats": stats,
        "category_obj": category_obj,
        "supplier_obj": supplier_obj,
        "subcategory_label": subcategory_label(subcategory) if subcategory else "",
        "stock_label": stock_labels.get(stock, ""),
        "query_base": _product_list_query(request, page=None),
        "qs_grid": _product_list_query(request, view="grid", page=None),
        "qs_list": _product_list_query(request, view="list", page=None),
        "qs_stock_all": _product_list_query(request, stock="", page=None),
        "qs_stock_available": _product_list_query(request, stock="AVAILABLE", page=None),
        "qs_stock_out": _product_list_query(request, stock="OUT", page=None),
        "qs_stock_none": _product_list_query(request, stock="NONE", page=None),
        "qs_clear_q": _product_list_query(request, q="", page=None),
        "qs_clear_category": _product_list_query(request, category="", page=None),
        "qs_clear_subcategory": _product_list_query(request, subcategory="", page=None),
        "qs_clear_supplier": _product_list_query(request, supplier="", page=None),
        "qs_clear_stock": _product_list_query(request, stock="", page=None),
        "qs_clear_all": _product_list_query(request, q="", category="", supplier="", subcategory="", stock="", page=None),
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


def _intake_context(result=None, report=None, datafile_report=None, datafile_error=""):
    locations = Location.objects.filter(is_active=True).order_by("name")
    return {
        "locations": locations,
        "default_location": default_location(),
        "result": result,
        "report": report,
        "datafile_report": datafile_report,
        "datafile_error": datafile_error,
    }


@login_required
def product_intake(request):
    """Default: jewellery Excel upload. One-piece form is the other way in."""
    if request.method == "POST" and request.POST.get("mode") == "datafile":
        if not is_developer(request.user):
            messages.error(request, "Print-sheet sync is only for the developer account.")
            return redirect("catalogue:product_list")
        try:
            datafile_report = sync_datafile()
        except RuntimeError as exc:
            return render(request, "catalogue/intake.html", _intake_context(datafile_error=str(exc)))
        return render(request, "catalogue/intake.html", _intake_context(datafile_report=datafile_report))

    if request.method == "POST":
        location = Location.objects.filter(
            pk=request.POST.get("location") or "", is_active=True,
        ).first() or default_location()
        if location is None:
            messages.error(request, "Add a location first. A new piece has to sit somewhere.")
            return render(request, "catalogue/intake.html", _intake_context())

        if request.POST.get("mode") == "one":
            row = IntakeRow(
                row_number=1,
                pj=(request.POST.get("pj") or "").strip().upper(),
                reference=(request.POST.get("reference") or "").strip(),
                owner=(request.POST.get("owner") or "").strip(),
                supplier=(request.POST.get("supplier") or "").strip(),
                subcategory=(request.POST.get("subcategory") or "").strip().upper(),
                metal_name=(request.POST.get("metal_name") or "").strip(),
                purity=(request.POST.get("purity") or "").strip(),
                weight=(request.POST.get("weight") or "").strip(),
                actual_price=None,
                currency=(request.POST.get("currency") or "USD").strip().upper(),
                rate=None,
                payment_type="",
                markup=None,
                markup_amount=None,
                size=(request.POST.get("size") or "").strip(),
                diamond_weight="",
            )
            from apps.catalogue.intake import _decimal
            row.actual_price = _decimal(request.POST.get("actual_price"))
            row.rate = _decimal(request.POST.get("rate"))
            if not row.pj or not row.reference or not row.owner:
                messages.error(request, "PJ code, supplier product code, and owner are required.")
                return render(request, "catalogue/intake.html", _intake_context())
            report = apply_rows([row], location)
            messages.success(
                request,
                f"Saved {row.pj}. {report['created']} new, {report['updated']} updated.",
            )
            return redirect("catalogue:item_detail", barcode=row.pj)

        upload = request.FILES.get("workbook")
        if not upload:
            messages.error(request, "Choose the jewellery Excel file first.")
            return render(request, "catalogue/intake.html", _intake_context())
        parsed = parse_jewellery_workbook(upload)
        if parsed.errors and not parsed.rows:
            return render(request, "catalogue/intake.html", _intake_context(result=parsed))
        report = apply_rows(parsed.rows, location)
        return render(request, "catalogue/intake.html", _intake_context(result=parsed, report=report))

    return render(request, "catalogue/intake.html", _intake_context())
