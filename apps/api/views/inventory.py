from django.db.models import Q
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets
from rest_framework.exceptions import ParseError

from apps.inventory.models import ProductItem

from ..mixins import ApiClientReadMixin
from ..serializers import ProductItemSerializer


class ProductItemViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    """
    Physical stock items. Detail lookup by barcode
    (``/items/PJ12345/``).

    Filters: ``?barcode=``, ``?status=``, ``?location=`` (location code),
    ``?product_id=``, ``?q=`` (barcode / product name / reference_id),
    ``?updated_since=``
    """

    serializer_class = ProductItemSerializer
    lookup_field = "barcode"
    lookup_url_kwarg = "barcode"
    lookup_value_regex = r"[^/]+"

    def get_queryset(self):
        qs = (
            ProductItem.objects.select_related("product", "location")
            .all()
            .order_by("barcode")
        )

        barcode = self.request.query_params.get("barcode")
        if barcode:
            qs = qs.filter(barcode__iexact=barcode)

        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status__iexact=status)

        location = self.request.query_params.get("location")
        if location:
            qs = qs.filter(location__code__iexact=location)

        product_id = self.request.query_params.get("product_id")
        if product_id:
            qs = qs.filter(product_id=product_id)

        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(barcode__icontains=q)
                | Q(product__name__icontains=q)
                | Q(product__reference_id__icontains=q)
            )

        updated_since = self.request.query_params.get("updated_since")
        if updated_since:
            dt = parse_datetime(updated_since)
            if dt is None:
                raise ParseError("updated_since must be an ISO-8601 datetime.")
            qs = qs.filter(updated_at__gte=dt)

        return qs
