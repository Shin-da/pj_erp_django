from rest_framework import serializers

from apps.tracker.models import TrackerScanItem, TrackerSession

from .common import EmployeeMiniSerializer


class TrackerScanItemSerializer(serializers.ModelSerializer):
    barcode = serializers.CharField(source="item.barcode", default="")
    location_at_scan_code = serializers.SerializerMethodField()

    class Meta:
        model = TrackerScanItem
        fields = [
            "id",
            "barcode",
            "result",
            "location_at_scan_code",
            "is_extra",
            "created_at",
            "updated_at",
        ]

    def get_location_at_scan_code(self, obj):
        return obj.location_at_scan.code if obj.location_at_scan_id else ""


class TrackerSessionSerializer(serializers.ModelSerializer):
    location_id = serializers.IntegerField(read_only=True)
    location_code = serializers.CharField(source="location.code", default="")
    location_name = serializers.CharField(source="location.name", default="")
    parent_session_id = serializers.IntegerField(read_only=True, allow_null=True)
    transfer_id = serializers.IntegerField(read_only=True, allow_null=True)
    created_by = EmployeeMiniSerializer(read_only=True, allow_null=True)
    scans = TrackerScanItemSerializer(source="scan_items", many=True, read_only=True)

    class Meta:
        model = TrackerSession
        fields = [
            "id",
            "scan_index",
            "mode",
            "location_id",
            "location_code",
            "location_name",
            "parent_session_id",
            "item_count",
            "is_transfer",
            "transfer_id",
            "created_by",
            "scans",
            "created_at",
            "updated_at",
        ]


class TrackerSessionListSerializer(TrackerSessionSerializer):
    class Meta(TrackerSessionSerializer.Meta):
        fields = [f for f in TrackerSessionSerializer.Meta.fields if f != "scans"]
