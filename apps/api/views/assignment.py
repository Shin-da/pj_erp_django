from django.db.models import Count, Prefetch, Q
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets
from rest_framework.exceptions import ParseError

from apps.assignment.models import (
    AssignmentLine,
    AssignmentMaster,
    Reseller,
    ResellerGroup,
    ResellerLocation,
)

from ..mixins import ApiClientReadMixin
from ..serializers import (
    AssignmentMasterListSerializer,
    AssignmentMasterSerializer,
    ResellerGroupSerializer,
    ResellerLocationSerializer,
    ResellerSerializer,
)


class ResellerGroupViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ResellerGroupSerializer
    queryset = ResellerGroup.objects.filter(is_active=True).order_by("name")

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        return qs


class ResellerLocationViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ResellerLocationSerializer
    queryset = ResellerLocation.objects.filter(is_active=True).order_by("name")


class ResellerViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ResellerSerializer

    def get_queryset(self):
        qs = (
            Reseller.objects.select_related("group")
            .filter(is_active=True)
            .order_by("name")
        )
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(reference_code__icontains=q)
                | Q(email__icontains=q)
            )
        group = self.request.query_params.get("group")
        if group:
            qs = qs.filter(Q(group__code__iexact=group) | Q(group_id=group))
        return qs


class AssignmentMasterViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    """
    Reseller invoices / assignments (SoftDelete — cancelled-deleted hidden).

    Filters: ``?invoice_number=``, ``?status=``, ``?reseller=`` (id),
    ``?q=`` (invoice number / reseller name), ``?updated_since=``
    """

    lookup_field = "pk"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return AssignmentMasterSerializer
        return AssignmentMasterListSerializer

    def get_queryset(self):
        lines_qs = AssignmentLine.objects.select_related(
            "item", "item__product"
        ).order_by("id")
        qs = (
            AssignmentMaster.objects.select_related(
                "reseller",
                "reseller_location",
                "created_by",
            )
            .annotate(annotated_line_count=Count("lines"))
            .order_by("-created_at", "-id")
        )
        if self.action == "retrieve":
            qs = qs.prefetch_related(Prefetch("lines", queryset=lines_qs))

        invoice_number = self.request.query_params.get("invoice_number")
        if invoice_number:
            qs = qs.filter(invoice_number__iexact=invoice_number)

        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(invoice_status__iexact=status)

        reseller = self.request.query_params.get("reseller")
        if reseller:
            qs = qs.filter(reseller_id=reseller)

        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(invoice_number__icontains=q) | Q(reseller__name__icontains=q)
            )

        updated_since = self.request.query_params.get("updated_since")
        if updated_since:
            dt = parse_datetime(updated_since)
            if dt is None:
                raise ParseError("updated_since must be an ISO-8601 datetime.")
            qs = qs.filter(updated_at__gte=dt)

        return qs
