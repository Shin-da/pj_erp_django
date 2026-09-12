from rest_framework import serializers

from apps.inventory.models import ProductItem


class ProductItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)
    product_reference_id = serializers.CharField(source="product.reference_id", default="")
    product_name = serializers.CharField(source="product.name", default="")
    location_id = serializers.IntegerField(read_only=True)
    location_code = serializers.CharField(source="location.code", default="")
    location_name = serializers.CharField(source="location.name", default="")

    class Meta:
        model = ProductItem
        fields = [
            "id",
            "barcode",
            "rfid_epc",
            "status",
            "reprint_status",
            "product_id",
            "product_reference_id",
            "product_name",
            "location_id",
            "location_code",
            "location_name",
            "created_at",
            "updated_at",
        ]
