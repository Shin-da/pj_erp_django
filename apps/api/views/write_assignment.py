from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assignment.models import AssignmentMaster, DisplaySlot, Reseller
from apps.assignment.services import create_invoice

from ..mixins import EmployeeWriteMixin
from ..serializers import AssignmentMasterSerializer


class InvoiceLineWriteSerializer(serializers.Serializer):
    barcode = serializers.CharField(max_length=100)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=Decimal("0")
    )
    commission_type = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    commission_rate = serializers.DecimalField(
        max_digits=10, decimal_places=4, required=False, allow_null=True, default=None
    )


class InvoiceCreateSerializer(serializers.Serializer):
    reseller_id = serializers.IntegerField()
    is_reserve = serializers.BooleanField(required=False, default=False)
    display_slot_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    lines = InvoiceLineWriteSerializer(many=True)


class InvoiceCreateView(EmployeeWriteMixin, APIView):
    """POST /api/v1/invoices/create/"""

    required_permission = "assignment.can_create_invoice"

    def post(self, request):
        ser = InvoiceCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        reseller = get_object_or_404(Reseller, pk=data["reseller_id"], is_active=True)
        display_slot = None
        if data.get("display_slot_id"):
            display_slot = get_object_or_404(DisplaySlot, pk=data["display_slot_id"])
        try:
            master = create_invoice(
                reseller=reseller,
                lines=data["lines"],
                actor=request.user,
                is_reserve=data.get("is_reserve", False),
                display_slot=display_slot,
            )
        except DjangoValidationError as exc:
            detail = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

        master = (
            AssignmentMaster.objects.select_related(
                "reseller", "reseller_location", "created_by"
            )
            .prefetch_related("lines__item__product")
            .get(pk=master.pk)
        )
        out = AssignmentMasterSerializer(master, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)


class InvoiceStampView(EmployeeWriteMixin, APIView):
    """POST /api/v1/invoices/{pk}/stamp/"""

    required_permission = "assignment.can_stamp_invoice"

    def post(self, request, pk):
        master = get_object_or_404(
            AssignmentMaster.objects.select_related(
                "reseller", "reseller_location", "created_by"
            ).prefetch_related("lines__item__product"),
            pk=pk,
        )
        master.stamp_invoice(actor=request.user)
        master.refresh_from_db()
        out = AssignmentMasterSerializer(master, context={"request": request})
        return Response(out.data)
