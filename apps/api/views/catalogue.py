from django.db.models import Q
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets
from rest_framework.exceptions import ParseError

from apps.catalogue.models import Category, Currency, Metal, ProductMaster, Purity, Supplier

from ..mixins import ApiClientReadMixin
from ..serializers import (
    CategorySerializer,
    CurrencySerializer,
    MetalSerializer,
    ProductMasterSerializer,
    PuritySerializer,
    SupplierSerializer,
)


class ProductViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    """
    Read-only product catalogue for external ApiClient keys.

    Detail lookup is by stable primary key (``/products/{id}/``).
    ``reference_id`` is filter-only because it is not unique in live data.

    Query params:
      ?reference_id=   exact, case-insensitive (may return multiple)
      ?category=       Category.code
      ?is_verified=true|false
      ?updated_since=<ISO datetime>
      ?page=&page_size=
    """

    serializer_class = ProductMasterSerializer
    lookup_field = "pk"
    lookup_url_kwarg = "pk"

    def get_queryset(self):
        qs = (
            ProductMaster.objects.select_related(
                "category", "currency", "supplier", "metal", "purity"
            )
            .prefetch_related("images")
            .filter(is_active=True)
            .order_by("id")
        )

        reference_id = self.request.query_params.get("reference_id")
        if reference_id:
            qs = qs.filter(reference_id__iexact=reference_id)

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__code__iexact=category)

        is_verified = self.request.query_params.get("is_verified")
        if is_verified is not None:
            qs = qs.filter(is_verified=is_verified.lower() in ("1", "true", "yes"))

        updated_since = self.request.query_params.get("updated_since")
        if updated_since:
            dt = parse_datetime(updated_since)
            if dt is None:
                raise ParseError("updated_since must be an ISO-8601 datetime.")
            qs = qs.filter(updated_at__gte=dt)

        return qs


class CategoryViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer
    queryset = Category.objects.all().order_by("name")
    lookup_field = "pk"


class CurrencyViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = CurrencySerializer
    queryset = Currency.objects.all().order_by("code")
    lookup_field = "pk"


class MetalViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = MetalSerializer
    queryset = Metal.objects.all().order_by("name")
    lookup_field = "pk"


class PurityViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = PuritySerializer
    queryset = Purity.objects.select_related("metal").order_by("metal__name", "name")
    lookup_field = "pk"


class SupplierViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = SupplierSerializer
    queryset = Supplier.objects.all().order_by("name")
    lookup_field = "pk"

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(reference_code__icontains=q))
        return qs
