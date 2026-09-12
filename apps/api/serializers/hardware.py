from rest_framework import serializers

from apps.hardware.models import LabelField, LabelPrintLog, LabelTemplate

from .common import EmployeeMiniSerializer


class LabelFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabelField
        fields = [
            "id",
            "field_key",
            "static_text",
            "x",
            "y",
            "font_size",
            "bold",
            "align",
            "box_width",
            "visible",
            "order",
        ]


class LabelTemplateSerializer(serializers.ModelSerializer):
    fields = LabelFieldSerializer(many=True, read_only=True)

    class Meta:
        model = LabelTemplate
        fields = [
            "id",
            "name",
            "category",
            "is_default",
            "media_profile",
            "dpi",
            "width_dots",
            "height_dots",
            "offset_x",
            "offset_y",
            "fields",
            "created_at",
            "updated_at",
        ]


class LabelTemplateListSerializer(LabelTemplateSerializer):
    class Meta(LabelTemplateSerializer.Meta):
        fields = [f for f in LabelTemplateSerializer.Meta.fields if f != "fields"]


class LabelPrintLogSerializer(serializers.ModelSerializer):
    printed_by = EmployeeMiniSerializer(read_only=True, allow_null=True)
    template_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = LabelPrintLog
        fields = [
            "id",
            "batch_id",
            "barcode",
            "template_id",
            "template_name",
            "printed_by",
            "printer_name",
            "quantity",
            "status",
            "error_message",
            "created_at",
            "updated_at",
        ]
