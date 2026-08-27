from django.contrib import admin

from .models import (
    AssignmentLine,
    AssignmentMaster,
    DisplaySlot,
    DisplaySlotAllotment,
    Reseller,
    ResellerGroup,
)


class ResellerInline(admin.TabularInline):
    model = Reseller
    extra = 0
    fields = ("name", "reference_code", "is_active")
    show_change_link = True


@admin.register(ResellerGroup)
class ResellerGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "client_count", "is_active")
    search_fields = ("name", "code")
    list_filter = ("is_active",)
    inlines = [ResellerInline]

    @admin.display(description="Clients")
    def client_count(self, obj):
        return obj.clients.count()


@admin.register(Reseller)
class ResellerAdmin(admin.ModelAdmin):
    list_display = ("name", "reference_code", "group", "is_active")
    search_fields = ("name", "reference_code")
    list_filter = ("group", "is_active")
    autocomplete_fields = ("group",)


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
    fields = (
        "item",
        "unit_price",
        "discount_percent",
        "commission_type",
        "commission_rate",
        "commission_value",
        "commission_overridden",
    )
    readonly_fields = ("commission_value",)


@admin.register(AssignmentMaster)
class AssignmentMasterAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "reseller", "invoice_status", "is_reserve", "created_at")
    list_filter = ("invoice_status", "is_reserve")
    search_fields = ("invoice_number", "reseller__name")
    autocomplete_fields = ("reseller", "display_slot")
    inlines = [AssignmentLineInline]


@admin.register(AssignmentLine)
class AssignmentLineAdmin(admin.ModelAdmin):
    list_display = (
        "master",
        "item",
        "unit_price",
        "discount_percent",
        "commission_type",
        "commission_value",
        "commission_overridden",
    )
    list_filter = ("commission_type", "commission_overridden")
    search_fields = ("master__id", "item__barcode")
    autocomplete_fields = ("master", "item")
    readonly_fields = ("commission_value",)
