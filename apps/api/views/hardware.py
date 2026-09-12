from django.db.models import Prefetch, Q
from rest_framework import viewsets

from apps.hardware.models import LabelField, LabelPrintLog, LabelTemplate

from ..mixins import ApiClientReadMixin
from ..serializers import (
    LabelPrintLogSerializer,
    LabelTemplateListSerializer,
    LabelTemplateSerializer,
)


class LabelTemplateViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    """Filters: ``?category=``, ``?is_default=true``"""

    lookup_field = "pk"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return LabelTemplateSerializer
        return LabelTemplateListSerializer

    def get_queryset(self):
        fields_qs = LabelField.objects.order_by("order", "id")
        qs = LabelTemplate.objects.order_by("category", "name")
        if self.action == "retrieve":
            qs = qs.prefetch_related(Prefetch("fields", queryset=fields_qs))

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__iexact=category)

        is_default = self.request.query_params.get("is_default")
        if is_default is not None:
            qs = qs.filter(is_default=is_default.lower() in ("1", "true", "yes"))

        return qs


class LabelPrintLogViewSet(ApiClientReadMixin, viewsets.ReadOnlyModelViewSet):
    """Filters: ``?barcode=``, ``?status=``, ``?batch_id=``, ``?q=``"""

    serializer_class = LabelPrintLogSerializer
    lookup_field = "pk"

    def get_queryset(self):
        qs = LabelPrintLog.objects.select_related("printed_by", "template").order_by(
            "-created_at", "-id"
        )

        barcode = self.request.query_params.get("barcode")
        if barcode:
            qs = qs.filter(barcode__iexact=barcode)

        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status__iexact=status)

        batch_id = self.request.query_params.get("batch_id")
        if batch_id:
            qs = qs.filter(batch_id=batch_id)

        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(barcode__icontains=q)
                | Q(template_name__icontains=q)
                | Q(printer_name__icontains=q)
            )

        return qs
