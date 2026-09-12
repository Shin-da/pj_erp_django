from rest_framework import serializers

from apps.catalogue.models import ProductImage, ProductMaster


class ProductImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["url", "kind", "is_primary", "caption", "order"]

    def get_url(self, obj):
        request = self.context.get("request")
        if not obj.image:
            return None
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url


class ProductMasterSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source="category.name", default="")
    currency = serializers.CharField(source="currency.code", default="")
    metal = serializers.CharField(source="display_metal", default="")
    purity = serializers.CharField(source="display_purity", default="")
    supplier = serializers.CharField(source="supplier.name", default="")
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = ProductMaster
        fields = [
            "id",
            "reference_id",
            "name",
            "category",
            "subcategory",
            "metal",
            "purity",
            "colour",
            "size",
            "quality",
            "stone",
            "net_weight",
            "gross_weight",
            "selling_price",
            "currency",
            "supplier",
            "is_active",
            "is_verified",
            "created_at",
            "updated_at",
            "images",
        ]
