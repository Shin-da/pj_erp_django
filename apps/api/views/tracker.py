from django.db.models import Prefetch
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets
from rest_framework.exceptions import ParseError

from apps.tracker.models import TrackerScanItem, TrackerSession

from ..mixins import ApiClientReadMixin
from ..serializers import TrackerSessionListSerializer, TrackerSessionSerializer


class TrackerSessionViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    """
    Lookup by ``scan_index`` (``/tracker-sessions/42/``).

    Filters: ``?mode=``, ``?location=`` (code), ``?updated_since=``
    """

    lookup_field = "scan_index"
    lookup_url_kwarg = "scan_index"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return TrackerSessionSerializer
        return TrackerSessionListSerializer

    def get_queryset(self):
        scans = TrackerScanItem.objects.select_related(
            "item", "location_at_scan"
        ).order_by("id")
        qs = TrackerSession.objects.select_related(
            "location", "created_by", "parent_session"
        ).order_by("-scan_index")
        if self.action == "retrieve":
            qs = qs.prefetch_related(Prefetch("scan_items", queryset=scans))

        mode = self.request.query_params.get("mode")
        if mode:
            qs = qs.filter(mode__iexact=mode)

        location = self.request.query_params.get("location")
        if location:
            qs = qs.filter(location__code__iexact=location)

        updated_since = self.request.query_params.get("updated_since")
        if updated_since:
            dt = parse_datetime(updated_since)
            if dt is None:
                raise ParseError("updated_since must be an ISO-8601 datetime.")
            qs = qs.filter(updated_at__gte=dt)

        return qs
