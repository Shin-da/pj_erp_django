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
    PhotoUploadBatch,
    StagedProductImage,
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
    fields = ("preview", "image", "thumbnail", "kind", "is_primary", "caption", "order", "source_filename")
    readonly_fields = ("preview", "source_filename")

    @admin.display(description="Preview")
    def preview(self, obj):
        src = ""
        if obj and obj.thumbnail:
            src = obj.thumbnail.url
        elif obj and obj.image:
            src = obj.image.url
        if src:
            return format_html(
                '<img src="{}" style="max-height:90px;max-width:120px;border-radius:4px" />',
                src,
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


@admin.register(PhotoUploadBatch)
class PhotoUploadBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id", "created_at", "mode", "uploaded_by", "target_code",
        "files_total", "attached_count", "staged_count", "source",
    )
    list_filter = ("mode",)
    search_fields = ("target_code", "note", "source", "uploaded_by__employee_code")
    readonly_fields = ("created_at", "updated_at")


@admin.register(StagedProductImage)
class StagedProductImageAdmin(admin.ModelAdmin):
    list_display = (
        "id", "source_filename", "hinted_code", "status", "batch", "product", "created_at",
    )
    list_filter = ("status", "kind")
    search_fields = ("source_filename", "hinted_code", "status_detail")
    autocomplete_fields = ("product", "product_image")
    readonly_fields = ("created_at", "updated_at", "attached_at", "discarded_at")
