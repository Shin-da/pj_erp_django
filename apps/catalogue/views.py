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

C2 fix (SYSTEM-AUDIT-2026-09-11.md): write views here are gated by real
permissions instead of just @login_required — see
apps/accounts/access.py::require_perm and apps/accounts/permissions.py.

  product_intake       — catalogue.can_intake_stock  (Excel / one-piece stock)
  product_photo_upload — catalogue.can_upload_photos (design photos by PJ)

Same employee login; separate people and screens. Photos still attach to
the design via barcode → ProductMaster → ProductImage (see photos.py).
Everything else on this page stays read-only/@login_required; view-only
access was never the security gap the audit found.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q, Subquery, Sum
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import urlencode

from apps.accounts.access import is_developer, require_perm
from apps.catalogue.consignment import NEAR_DAYS, decorate_due_rows, due_horizon
from apps.catalogue.datafile import sync_datafile
from apps.catalogue.intake import (
    TEMPLATE_FILENAME,
    IntakeRow,
    apply_rows,
    build_jewellery_template,
    default_location,
    parse_jewellery_workbook,
    record_intake_batch,
)
from apps.catalogue.labels import subcategory_label
from apps.catalogue.models import (
    Category,
    ProductImage,
    ProductIntakeBatch,
    ProductMaster,
    PurchaseType,
    Supplier,
)
from apps.catalogue.photos import (
    attach_bulk_by_filename,
    attach_uploaded_images,
    delete_all_product_images,
    delete_product_image,
    normalize_code,
    resolve_product_by_code,
)
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
        "purchase": request.GET.get("purchase", "").strip(),
        "due": request.GET.get("due", "").strip(),
        "media": request.GET.get("media", "").strip(),
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
    has_photo = Exists(ProductImage.objects.filter(product_id=OuterRef("pk")))
    products = (
        ProductMaster.objects.select_related("category", "currency", "metal", "purity", "supplier")
        .prefetch_related("images")
        .annotate(**_stock_annotations(), sample_barcode=sample_barcode, has_photo=has_photo)
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
        with_photos=Count("pk", filter=Q(has_photo=True)),
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

    purchase = request.GET.get("purchase", "").strip()
    if purchase in {PurchaseType.PURCHASED, PurchaseType.CONSIGNMENT}:
        products = products.filter(product_type=purchase)

    media = request.GET.get("media", "").strip()
    if media == "photos":
        products = products.filter(has_photo=True)
    elif media == "none":
        products = products.filter(has_photo=False)

    today, horizon = due_horizon()
    due = request.GET.get("due", "").strip()
    if due in {"overdue", "today", "soon", "open"}:
        products = products.filter(
            product_type=PurchaseType.CONSIGNMENT,
            due_date__isnull=False,
        )
        if due == "overdue":
            products = products.filter(due_date__lt=today)
        elif due == "today":
            products = products.filter(due_date=today)
        elif due == "soon":
            products = products.filter(due_date__gt=today, due_date__lte=horizon)
        else:
            products = products.filter(due_date__lte=horizon)

    view = request.GET.get("view", "grid").strip()
    if view not in ("grid", "list", "piece"):
        view = "grid"

    # Default by reference_id: many legacy designs share a style name
    # (e.g. ANICH1) while the reference is what actually distinguishes them.
    # Piece view defaults to barcode instead — that's the one field that's
    # actually unique per row there.
    default_sort = "barcode" if view == "piece" else "reference"
    sort = request.GET.get("sort", default_sort).strip() or default_sort
    if due and sort in ("reference", "barcode"):
        sort = "due"

    if view == "piece":
        # One row per physical piece (inventory.ProductItem) instead of per
        # design. Same filters as the design query above, re-applied one
        # level down through `product__` — except "stock", which is
        # deliberately reinterpreted: at design level AVAILABLE means "has
        # at least one available piece"; here it means "this piece is
        # available", i.e. a real per-item status rather than a rollup.
        items = (
            ProductItem.objects.select_related(
                "product", "product__category", "product__currency", "location"
            )
            .prefetch_related("product__images")
        )
        if q:
            items = items.filter(
                Q(barcode__icontains=q)
                | Q(product__name__icontains=q)
                | Q(product__reference_id__icontains=q)
                | Q(product__subcategory__icontains=q)
            )
        if category:
            items = items.filter(product__category__code=category)
        if supplier:
            items = items.filter(product__supplier_id=supplier)
        if subcategory:
            items = items.filter(product__subcategory=subcategory)
        if purchase in {PurchaseType.PURCHASED, PurchaseType.CONSIGNMENT}:
            items = items.filter(product__product_type=purchase)
        if media == "photos":
            items = items.filter(Exists(ProductImage.objects.filter(product_id=OuterRef("product_id"))))
        elif media == "none":
            items = items.filter(~Exists(ProductImage.objects.filter(product_id=OuterRef("product_id"))))
        if due in {"overdue", "today", "soon", "open"}:
            items = items.filter(
                product__product_type=PurchaseType.CONSIGNMENT,
                product__due_date__isnull=False,
            )
            if due == "overdue":
                items = items.filter(product__due_date__lt=today)
            elif due == "today":
                items = items.filter(product__due_date=today)
            elif due == "soon":
                items = items.filter(product__due_date__gt=today, product__due_date__lte=horizon)
            else:
                items = items.filter(product__due_date__lte=horizon)
        if stock == "AVAILABLE":
            items = items.filter(status=StockStatus.PENDING)
        elif stock == "SOLD":
            items = items.filter(status=StockStatus.SOLD)
        elif stock == "ASSIGNED":
            items = items.filter(status=StockStatus.ASSIGNED)
        elif stock == "OUT":
            # Design-level "nothing available" has no single-piece meaning
            # of its own — the nearest honest equivalent is "this piece
            # isn't the available one".
            items = items.exclude(status=StockStatus.PENDING)
        elif stock == "NONE":
            # "No pieces at all" describes designs with zero items — by
            # definition there is no piece row to show for them.
            items = items.none()

        piece_sort_map = {
            "reference": ("product__reference_id", "barcode"),
            "-reference": ("-product__reference_id", "-barcode"),
            "name": ("product__name", "barcode"),
            "-name": ("-product__name", "-barcode"),
            "barcode": ("barcode",),
            "-barcode": ("-barcode",),
            "price": ("product__selling_price", "barcode"),
            "-price": ("-product__selling_price", "barcode"),
            "due": ("product__due_date", "barcode"),
            "-due": ("-product__due_date", "barcode"),
        }
        items = items.order_by(*piece_sort_map.get(sort, piece_sort_map["barcode"]))

        per_page = 50
        paginator = Paginator(items, per_page)
        page_obj = paginator.get_page(request.GET.get("page"))
        decorate_due_rows([it.product for it in page_obj], today=today)
    else:
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
            "due": ("due_date", "name"),
            "-due": ("-due_date", "name"),
        }
        products = products.order_by(*sort_map.get(sort, sort_map["reference"]))

        per_page = 24 if view == "grid" else 50
        paginator = Paginator(products, per_page)
        page_obj = paginator.get_page(request.GET.get("page"))
        decorate_due_rows(page_obj.object_list, today=today)

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

    due_labels = {
        "overdue": "Consignment overdue",
        "today": "Consignment due today",
        "soon": f"Consignment due within {NEAR_DAYS} days",
        "open": "Consignment due soon or overdue",
    }
    purchase_labels = {
        PurchaseType.PURCHASED: "Purchased",
        PurchaseType.CONSIGNMENT: "Consignment",
    }
    media_labels = {
        "photos": "Has photos",
        "none": "No photos",
    }

    return render(request, "catalogue/product_list.html", {
        "page_obj": page_obj,
        "q": q,
        "category": category,
        "supplier": supplier,
        "subcategory": subcategory,
        "stock": stock,
        "purchase": purchase,
        "due": due,
        "media": media,
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
        "purchase_label": purchase_labels.get(purchase, ""),
        "due_label": due_labels.get(due, ""),
        "media_label": media_labels.get(media, ""),
        "query_base": _product_list_query(request, page=None),
        "qs_grid": _product_list_query(request, view="grid", page=None),
        "qs_list": _product_list_query(request, view="list", page=None),
        "qs_piece": _product_list_query(request, view="piece", page=None),
        "qs_stock_all": _product_list_query(request, stock="", page=None),
        "qs_stock_available": _product_list_query(request, stock="AVAILABLE", page=None),
        "qs_stock_out": _product_list_query(request, stock="OUT", page=None),
        "qs_stock_none": _product_list_query(request, stock="NONE", page=None),
        "qs_media_photos": _product_list_query(request, media="photos", page=None),
        "qs_media_all": _product_list_query(request, media="", page=None),
        "qs_clear_q": _product_list_query(request, q="", page=None),
        "qs_clear_category": _product_list_query(request, category="", page=None),
        "qs_clear_subcategory": _product_list_query(request, subcategory="", page=None),
        "qs_clear_supplier": _product_list_query(request, supplier="", page=None),
        "qs_clear_stock": _product_list_query(request, stock="", page=None),
        "qs_clear_purchase": _product_list_query(request, purchase="", page=None),
        "qs_clear_due": _product_list_query(request, due="", page=None),
        "qs_clear_media": _product_list_query(request, media="", page=None),
        "qs_clear_all": _product_list_query(
            request, q="", category="", supplier="", subcategory="", stock="",
            purchase="", due="", media="", page=None,
        ),
    })

@login_required
def product_detail(request, pk):
    """One design: its spec sheet, its stock rollup, and every piece of it."""
    product = get_object_or_404(
        ProductMaster.objects.select_related("category", "currency", "metal", "purity", "supplier")
        .prefetch_related("images")
        .annotate(**_stock_annotations()),
        pk=pk,
    )

    decorate_due_rows([product])

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
        # Prefer a real piece barcode for the photo upload deep-link;
        # reference_id is often a supplier code, not PJ….
        "photo_lookup_code": (
            ProductItem.objects.filter(product=product)
            .order_by("barcode")
            .values_list("barcode", flat=True)
            .first()
            or product.reference_id
            or ""
        ),
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
        ).prefetch_related("product__images"),
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


def _intake_history(request):
    batches = ProductIntakeBatch.objects.select_related("uploaded_by", "location")
    paginator = Paginator(batches, 25)
    return paginator.get_page(request.GET.get("page"))


def _intake_context(request, result=None, report=None, datafile_report=None, datafile_error=""):
    locations = Location.objects.filter(is_active=True).order_by("name")
    return {
        "locations": locations,
        "default_location": default_location(),
        "result": result,
        "report": report,
        "datafile_report": datafile_report,
        "datafile_error": datafile_error,
        "history": _intake_history(request),
        "template_filename": TEMPLATE_FILENAME,
    }


@require_perm("catalogue.can_intake_stock")
def product_intake(request):
    """
    Default: jewellery Excel upload. One-piece form is the other way in.

    C2 fix: this is the view that actually creates/updates stock
    (ProductMaster/ProductItem via apply_rows()), so it's gated by
    `catalogue.can_intake_stock` — see require_perm in accounts/access.py.
    The datafile/is_developer branch below is a separate, narrower gate
    (developer-only sync tooling) and is unaffected by this change.
    """
    if request.method == "POST" and request.POST.get("mode") == "datafile":
        if not is_developer(request.user):
            messages.error(request, "Print-sheet sync is only for the developer account.")
            return redirect("catalogue:product_list")
        try:
            datafile_report = sync_datafile()
        except RuntimeError as exc:
            return render(request, "catalogue/intake.html", _intake_context(request, datafile_error=str(exc)))
        return render(request, "catalogue/intake.html", _intake_context(request, datafile_report=datafile_report))

    if request.method == "POST":
        location = Location.objects.filter(
            pk=request.POST.get("location") or "", is_active=True,
        ).first() or default_location()
        if location is None:
            messages.error(request, "Add a location first. A new piece has to sit somewhere.")
            return render(request, "catalogue/intake.html", _intake_context(request))

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
                purchase_type=(request.POST.get("purchase_type") or "").strip(),
            )
            from apps.catalogue.intake import _decimal
            row.actual_price = _decimal(request.POST.get("actual_price"))
            row.rate = _decimal(request.POST.get("rate"))
            if not row.pj or not row.reference or not row.owner:
                messages.error(request, "PJ code, supplier product code, and owner are required.")
                return render(request, "catalogue/intake.html", _intake_context(request))
            report = apply_rows([row], location)
            record_intake_batch(
                user=request.user,
                location=location,
                filename=row.pj,
                raw_bytes=None,
                parsed=None,
                report=report,
                source=ProductIntakeBatch.Source.FORM,
            )
            messages.success(
                request,
                f"Saved {row.pj}. {report['created']} new, {report['updated']} updated.",
            )
            return redirect("catalogue:item_detail", barcode=row.pj)

        upload = request.FILES.get("workbook")
        if not upload:
            messages.error(request, "Choose the jewellery Excel file first.")
            return render(request, "catalogue/intake.html", _intake_context(request))
        from io import BytesIO
        raw = upload.read()
        parsed = parse_jewellery_workbook(BytesIO(raw))
        report = None
        if parsed.rows:
            report = apply_rows(parsed.rows, location)
        batch = record_intake_batch(
            user=request.user,
            location=location,
            filename=upload.name,
            raw_bytes=raw,
            parsed=parsed,
            report=report,
        )
        if parsed.errors and not parsed.rows:
            messages.error(request, "That file was not the jewellery upload.")
        else:
            messages.success(
                request,
                f"Upload {batch.serial_no}: {batch.created_count} new, {batch.updated_count} updated.",
            )
        return redirect("catalogue:intake_batch", pk=batch.pk)

    return render(request, "catalogue/intake.html", _intake_context(request))


@login_required
def intake_template(request):
    """Download Sample Excel — same Jewellery Excel layout as iadmin."""
    payload = build_jewellery_template()
    response = HttpResponse(
        payload,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{TEMPLATE_FILENAME}"'
    return response


@login_required
def intake_batch_detail(request, pk):
    """One upload after it lands — Excel Logs popup, as its own page."""
    batch = get_object_or_404(
        ProductIntakeBatch.objects.select_related("uploaded_by", "location"),
        pk=pk,
    )
    lines = batch.lines.select_related("item", "item__product", "item__location")
    return render(request, "catalogue/intake_batch.html", {
        "batch": batch,
        "lines": lines,
        "history": _intake_history(request),
        "template_filename": TEMPLATE_FILENAME,
    })


@login_required
def intake_batch_file(request, pk):
    batch = get_object_or_404(ProductIntakeBatch, pk=pk)
    if not batch.workbook:
        messages.error(request, "That upload did not keep the original file.")
        return redirect("catalogue:intake_batch", pk=batch.pk)
    return FileResponse(
        batch.workbook.open("rb"),
        as_attachment=True,
        filename=batch.filename or TEMPLATE_FILENAME,
    )


def _photo_upload_context(request, *, code="", product=None, bulk_report=None, lookup_error=""):
    from apps.catalogue.photos import _photo_limits

    sample_barcode = ""
    piece_count = 0
    photos = []
    if product is not None:
        sample = (
            ProductItem.objects.filter(product=product)
            .order_by("barcode")
            .values_list("barcode", flat=True)
            .first()
        )
        sample_barcode = sample or ""
        piece_count = ProductItem.objects.filter(product=product).count()
        photos = list(product.images.all())
    resize, quality, max_bytes = _photo_limits()
    return {
        "code": code,
        "product": product,
        "sample_barcode": sample_barcode,
        "piece_count": piece_count,
        "photos": photos,
        "bulk_report": bulk_report,
        "lookup_error": lookup_error,
        "photo_max_width": resize,
        "photo_max_mb": max(1, max_bytes // (1024 * 1024)),
        "photo_keeps_original": resize <= 0,
    }


@require_perm("catalogue.can_upload_photos")
def product_photo_upload(request):
    """
    Photo-team flow: look up a PJ / barcode, attach or remove files on that design.

    Separate from stock intake (`product_intake`). Does not create stock.
    Uses the same ProductImage rows the CLI imports and catalogue pages show.
    """
    if request.method == "POST":
        mode = (request.POST.get("mode") or "lookup").strip()

        if mode == "bulk":
            uploads = request.FILES.getlist("photos")
            if not uploads:
                messages.error(request, "Choose one or more image files named with a PJ code.")
                return render(request, "catalogue/photo_upload.html", _photo_upload_context(request))
            report = attach_bulk_by_filename(uploads)
            if report["created"]:
                messages.success(
                    request,
                    f"Attached {report['created']} photo(s) across "
                    f"{report['products_touched']} design(s).",
                )
            if report["skipped"]:
                messages.info(request, f"Skipped {report['skipped']} already-stored file(s).")
            if report["unmatched"]:
                messages.warning(
                    request,
                    f"{len(report['unmatched'])} file(s) could not be matched "
                    f"(missing PJ, unknown code, or over size limit).",
                )
            if not report["created"] and not report["skipped"] and report["unmatched"]:
                messages.error(
                    request,
                    "Nothing was attached — check filenames include a PJ code "
                    "and each file is under the size limit.",
                )
            return render(
                request,
                "catalogue/photo_upload.html",
                _photo_upload_context(request, bulk_report=report),
            )

        code = normalize_code(request.POST.get("code") or request.POST.get("pj") or "")
        if not code:
            messages.error(request, "Enter a PJ / barcode first.")
            return render(request, "catalogue/photo_upload.html", _photo_upload_context(request))

        product = resolve_product_by_code(code)
        if product is None:
            err = (
                f"No design found for {code}. Stock people add the piece first; "
                "photos attach to an existing PJ."
            )
            return render(
                request,
                "catalogue/photo_upload.html",
                _photo_upload_context(request, code=code, lookup_error=err),
            )

        if mode == "lookup":
            return redirect(f"{request.path}?code={code}")

        if mode == "delete":
            try:
                image_id = int(request.POST.get("image_id") or "0")
            except ValueError:
                image_id = 0
            image = ProductImage.objects.filter(pk=image_id, product=product).first()
            if image is None:
                messages.error(request, "That photo is not on this design.")
            else:
                delete_product_image(image)
                messages.success(request, "Photo removed.")
            return redirect(f"{request.path}?code={code}")

        if mode == "delete_all":
            removed = delete_all_product_images(product)
            if removed:
                messages.success(request, f"Removed {removed} photo(s) from {code}.")
            else:
                messages.info(request, "No photos to remove.")
            return redirect(f"{request.path}?code={code}")

        # mode == "upload"
        uploads = request.FILES.getlist("photos")
        if not uploads:
            messages.error(request, "Choose at least one photo to upload.")
            return render(
                request,
                "catalogue/photo_upload.html",
                _photo_upload_context(request, code=code, product=product),
            )

        result = attach_uploaded_images(product, uploads, caption=code)
        if result["created"]:
            messages.success(request, f"Attached {result['created']} photo(s) to {code}.")
        if result["skipped"]:
            messages.info(request, f"Skipped {result['skipped']} already-stored file(s).")
        for err in result["errors"]:
            messages.warning(request, err)
        if not result["created"] and not result["skipped"]:
            messages.error(request, "Nothing was attached.")
        return redirect(f"{request.path}?code={code}")

    code = normalize_code(request.GET.get("code") or "")
    product = resolve_product_by_code(code) if code else None
    lookup_error = ""
    if code and product is None:
        lookup_error = (
            f"No design found for {code}. Stock people add the piece first; "
            "photos attach to an existing PJ."
        )
    return render(
        request,
        "catalogue/photo_upload.html",
        _photo_upload_context(
            request, code=code, product=product, lookup_error=lookup_error,
        ),
    )
