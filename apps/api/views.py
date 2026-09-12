from django.utils.dateparse import parse_datetime
from rest_framework import viewsets
from rest_framework.exceptions import ParseError

from apps.catalogue.models import ProductMaster

from .serializers import ProductMasterSerializer


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only. Query params:
      ?reference_id=PJ12345   exact, case-insensitive
      ?category=JWL           by Category.code
      ?is_verified=true|false include/exclude almarphoto-only provisional rows
      ?updated_since=<ISO datetime>   for incremental polling
    """

    serializer_class = ProductMasterSerializer
    lookup_field = "reference_id"
    lookup_value_regex = r"[^/]+"

    def get_queryset(self):
        qs = (
            ProductMaster.objects.select_related("category", "currency", "supplier", "metal", "purity")
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
