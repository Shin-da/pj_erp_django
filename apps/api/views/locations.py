from django.db.models import Q
from rest_framework import viewsets

from apps.locations.models import Location

from ..mixins import ApiClientReadMixin
from ..serializers import LocationSerializer


class LocationViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    """
    Company stock locations (SoftDelete — default manager is active-only).

    Lookup by ``code`` (e.g. ``/locations/HO/``).
    Filters: ``?q=``, ``?location_type=``
    """

    serializer_class = LocationSerializer
    lookup_field = "code"
    lookup_url_kwarg = "code"
    lookup_value_regex = r"[^/]+"

    def get_queryset(self):
        qs = Location.objects.all().order_by("name")
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        location_type = self.request.query_params.get("location_type")
        if location_type:
            qs = qs.filter(location_type__iexact=location_type)
        return qs
