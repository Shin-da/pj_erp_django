from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets
from rest_framework.exceptions import ParseError

from apps.returns.models import ReserveAlert, ReturnRecord

from ..mixins import ApiClientReadMixin
from ..serializers import ReserveAlertSerializer, ReturnRecordSerializer


class ReturnRecordViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    """
    Filters: ``?barcode=``, ``?outcome=``, ``?invoice_number=``,
    ``?updated_since=``
    """

    serializer_class = ReturnRecordSerializer
    lookup_field = "pk"

    def get_queryset(self):
        qs = (
            ReturnRecord.objects.select_related(
                "item",
                "item__product",
                "assignment_line",
                "assignment_line__master",
                "reassigned_to",
                "processed_by",
            )
            .order_by("-created_at", "-id")
        )

        barcode = self.request.query_params.get("barcode")
        if barcode:
            qs = qs.filter(item__barcode__iexact=barcode)

        outcome = self.request.query_params.get("outcome")
        if outcome:
            qs = qs.filter(outcome__iexact=outcome)

        invoice_number = self.request.query_params.get("invoice_number")
        if invoice_number:
            qs = qs.filter(assignment_line__master__invoice_number__iexact=invoice_number)

        updated_since = self.request.query_params.get("updated_since")
        if updated_since:
            dt = parse_datetime(updated_since)
            if dt is None:
                raise ParseError("updated_since must be an ISO-8601 datetime.")
            qs = qs.filter(updated_at__gte=dt)

        return qs


class ReserveAlertViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    """
    Filters: ``?barcode=``, ``?reseller=`` (id), ``?open=true`` (unresolved),
    ``?overdue=true``
    """

    serializer_class = ReserveAlertSerializer
    lookup_field = "pk"

    def get_queryset(self):
        qs = (
            ReserveAlert.objects.select_related("item", "reseller")
            .order_by("expires_at", "id")
        )

        barcode = self.request.query_params.get("barcode")
        if barcode:
            qs = qs.filter(item__barcode__iexact=barcode)

        reseller = self.request.query_params.get("reseller")
        if reseller:
            qs = qs.filter(reseller_id=reseller)

        open_only = self.request.query_params.get("open")
        if open_only is not None and open_only.lower() in ("1", "true", "yes"):
            qs = qs.filter(resolved_at__isnull=True)

        overdue = self.request.query_params.get("overdue")
        if overdue is not None and overdue.lower() in ("1", "true", "yes"):
            qs = qs.filter(resolved_at__isnull=True, expires_at__lt=timezone.now())

        return qs
