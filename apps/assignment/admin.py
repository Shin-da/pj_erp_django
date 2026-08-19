from django.contrib import admin

from .models import Reseller, DisplaySlot, DisplaySlotAllotment, AssignmentMaster, AssignmentLine


@admin.register(Reseller)
class ResellerAdmin(admin.ModelAdmin):
    list_display = ("name", "reference_code", "is_active")
    search_fields = ("name", "reference_code")


@admin.register(DisplaySlot)
class DisplaySlotAdmin(admin.ModelAdmin):
    list_display = ("name", "capacity", "is_available")
    search_fields = ("name",)


@admin.register(DisplaySlotAllotment)
class DisplaySlotAllotmentAdmin(admin.ModelAdmin):
    list_display = ("slot", "reseller", "released_at")
    list_filter = ("slot",)


class AssignmentLineInline(admin.TabularInline):
    model = AssignmentLine
    extra = 0
    autocomplete_fields = ("item",)


@admin.register(AssignmentMaster)
class AssignmentMasterAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "reseller", "invoice_status", "is_reserve", "created_at")
    list_filter = ("invoice_status", "is_reserve")
    search_fields = ("=id", "reseller__name")
    autocomplete_fields = ("reseller", "display_slot")
    inlines = [AssignmentLineInline]


@admin.register(AssignmentLine)
class AssignmentLineAdmin(admin.ModelAdmin):
    list_display = ("master", "item", "unit_price", "discount_percent")
    search_fields = ("master__id", "item__barcode")
    autocomplete_fields = ("master", "item")
