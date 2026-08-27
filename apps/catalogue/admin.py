from django.contrib import admin

from .models import Category, Currency, Metal, Purity, Supplier, ProductMaster


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


@admin.register(ProductMaster)
class ProductMasterAdmin(admin.ModelAdmin):
    list_display = ("name", "reference_id", "category", "subcategory", "selling_price", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "reference_id", "subcategory")
    autocomplete_fields = ("category", "currency", "metal", "purity", "supplier")
