from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.assignment.models import AssignmentLine, AssignmentMaster, Reseller, ResellerGroup, ResellerLocation

from .common import EmployeeMiniSerializer


class ResellerGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResellerGroup
        fields = ["id", "name", "code", "is_active", "created_at", "updated_at"]


class ResellerLocationSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = ResellerLocation
        fields = [
            "id",
            "name",
            "remarks",
            "logo_url",
            "is_active",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_logo_url(self, obj):
        request = self.context.get("request")
        if not obj.logo:
            return None
        return request.build_absolute_uri(obj.logo.url) if request else obj.logo.url


class ResellerSerializer(serializers.ModelSerializer):
    group_id = serializers.IntegerField(read_only=True, allow_null=True)
    group_code = serializers.SerializerMethodField()

    class Meta:
        model = Reseller
        fields = [
            "id",
            "name",
            "reference_code",
            "address",
            "contact",
            "email",
            "group_id",
            "group_code",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def get_group_code(self, obj):
        return obj.group.code if obj.group_id else ""


class AssignmentLineSerializer(serializers.ModelSerializer):
    barcode = serializers.CharField(source="item.barcode", default="")
    product_name = serializers.CharField(source="item.product.name", default="")
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = AssignmentLine
        fields = [
            "id",
            "barcode",
            "product_name",
            "unit_price",
            "discount_percent",
            "line_total",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_line_total(self, obj):
        return obj.calculate_line_total()


class AssignmentMasterSerializer(serializers.ModelSerializer):
    reseller_id = serializers.IntegerField(read_only=True)
    reseller_name = serializers.CharField(source="reseller.name", default="")
    reseller_location_id = serializers.IntegerField(read_only=True, allow_null=True)
    reseller_location_name = serializers.SerializerMethodField()
    created_by = EmployeeMiniSerializer(read_only=True, allow_null=True)
    lines = AssignmentLineSerializer(many=True, read_only=True)
    line_count = serializers.SerializerMethodField()

    class Meta:
        model = AssignmentMaster
        fields = [
            "id",
            "invoice_number",
            "invoice_status",
            "is_reserve",
            "reseller_id",
            "reseller_name",
            "reseller_location_id",
            "reseller_location_name",
            "created_by",
            "line_count",
            "lines",
            "created_at",
            "updated_at",
        ]

    def get_reseller_location_name(self, obj):
        return obj.reseller_location.name if obj.reseller_location_id else ""

    @extend_schema_field(serializers.IntegerField())
    def get_line_count(self, obj):
        # Prefer annotation when present; fall back for retrieve.
        annotated = getattr(obj, "annotated_line_count", None)
        if annotated is not None:
            return annotated
        return obj.lines.count()


class AssignmentMasterListSerializer(AssignmentMasterSerializer):
    """List payload without nested lines (use retrieve for lines)."""

    class Meta(AssignmentMasterSerializer.Meta):
        fields = [
            f for f in AssignmentMasterSerializer.Meta.fields if f != "lines"
        ]
