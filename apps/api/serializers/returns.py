from rest_framework import serializers

from apps.returns.models import ReserveAlert, ReturnRecord

from .common import EmployeeMiniSerializer


class ReturnRecordSerializer(serializers.ModelSerializer):
    barcode = serializers.CharField(source="item.barcode", default="")
    product_name = serializers.CharField(source="item.product.name", default="")
    invoice_number = serializers.SerializerMethodField()
    reassigned_to_id = serializers.IntegerField(read_only=True, allow_null=True)
    reassigned_to_name = serializers.SerializerMethodField()
    processed_by = EmployeeMiniSerializer(read_only=True, allow_null=True)

    class Meta:
        model = ReturnRecord
        fields = [
            "id",
            "outcome",
            "barcode",
            "product_name",
            "invoice_number",
            "reassigned_to_id",
            "reassigned_to_name",
            "processed_by",
            "created_at",
            "updated_at",
        ]

    def get_invoice_number(self, obj):
        if not obj.assignment_line_id:
            return ""
        return obj.assignment_line.master.invoice_number or ""

    def get_reassigned_to_name(self, obj):
        return obj.reassigned_to.name if obj.reassigned_to_id else ""


class ReserveAlertSerializer(serializers.ModelSerializer):
    barcode = serializers.CharField(source="item.barcode", default="")
    reseller_id = serializers.IntegerField(read_only=True)
    reseller_name = serializers.CharField(source="reseller.name", default="")

    class Meta:
        model = ReserveAlert
        fields = [
            "id",
            "barcode",
            "reseller_id",
            "reseller_name",
            "expires_at",
            "resolved_at",
            "created_at",
            "updated_at",
        ]
