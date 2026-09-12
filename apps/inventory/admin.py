from django.contrib import admin

from .models import ProductItem


@admin.register(ProductItem)
class ProductItemAdmin(admin.ModelAdmin):
    list_display = ("barcode", "product", "location", "status", "updated_at")
    list_filter = ("status", "location")
    search_fields = ("barcode", "product__name", "product__reference_id")
    autocomplete_fields = ("product", "location")
