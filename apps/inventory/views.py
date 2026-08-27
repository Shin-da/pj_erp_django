from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from apps.inventory.models import ProductItem, StockStatus
from apps.locations.models import Location


@login_required
def location_list(request):
    """
    Stock by Location — replaces `locationbase_stock.aspx`'s grid-of-
    locations-with-totals view. The legacy page popped item detail up in
    an in-page overlay; here it's a real second page instead
    (`location_detail`), which also gets its own shareable/bookmarkable
    URL and pagination for free.
    """
    locations = (
        Location.objects.annotate(
            item_count=Count("items"),
            available_count=Count("items", filter=Q(items__status=StockStatus.PENDING)),
            assigned_count=Count("items", filter=Q(items__status=StockStatus.ASSIGNED)),
            sold_count=Count("items", filter=Q(items__status=StockStatus.SOLD)),
        )
        .order_by("name")
    )
    return render(request, "inventory/location_list.html", {"locations": locations})


@login_required
def location_detail(request, code):
    """Barcode-level stock list for one location — replaces the legacy popup grid."""
    location = get_object_or_404(Location, code=code)
    items = (
        ProductItem.objects.filter(location=location)
        .select_related("product", "product__category", "product__currency")
        .order_by("barcode")
    )

    q = request.GET.get("q", "").strip()
    if q:
        items = items.filter(
            Q(barcode__icontains=q)
            | Q(product__reference_id__icontains=q)
            | Q(product__name__icontains=q)
        )

    status = request.GET.get("status", "").strip()
    if status:
        items = items.filter(status=status)

    paginator = Paginator(items, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "inventory/location_detail.html",
        {
            "location": location,
            "page_obj": page_obj,
            "q": q,
            "status": status,
            "status_choices": StockStatus.choices,
        },
    )
