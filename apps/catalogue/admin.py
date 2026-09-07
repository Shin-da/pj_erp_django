from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Category,
    Currency,
    Metal,
    Purity,
    Supplier,
    ProductMaster,
    ProductImage,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "symbol")
    search_fields = ("code",)


@admin.register(Metal)
class MetalAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Purity)
class PurityAdmin(admin.ModelAdmin):
    list_display = ("metal", "name")
    list_filter = ("metal",)
    search_fields = ("name", "metal__name")


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "reference_code")
    search_fields = ("name", "reference_code")


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ("preview", "image", "kind", "is_primary", "caption", "order", "source_filename")
    readonly_fields = ("preview", "source_filename")

    @admin.display(description="Preview")
    def preview(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="max-height:90px;max-width:120px;border-radius:4px" />',
                obj.image.url,
            )
        return "—"


@admin.register(ProductMaster)
class ProductMasterAdmin(admin.ModelAdmin):
    list_display = (
        "name", "reference_id", "category", "subcategory",
        "gold_weight", "diamond_weight", "selling_price", "image_count", "is_active",
    )
    list_filter = ("category", "is_active")
    search_fields = ("name", "reference_id", "subcategory")
    autocomplete_fields = ("category", "currency", "metal", "purity", "supplier")
    inlines = (ProductImageInline,)

    @admin.display(description="Photos")
    def image_count(self, obj):
        return obj.images.count()


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "kind", "is_primary", "thumb", "source_filename", "created_at")
    list_filter = ("kind", "is_primary")
    search_fields = ("product__name", "product__reference_id", "source_filename")
    autocomplete_fields = ("product",)
    readonly_fields = ("thumb", "created_at", "updated_at")

    @admin.display(description="Preview")
    def thumb(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:70px;max-width:100px;border-radius:4px" />',
                obj.image.url,
            )
        return "—"
