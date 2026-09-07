from django.contrib import admin

from .models import LabelField, LabelPrintLog, LabelTemplate


class LabelFieldInline(admin.TabularInline):
    model = LabelField
    extra = 0


@admin.register(LabelTemplate)
class LabelTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "media_profile", "is_default", "width_dots", "height_dots", "offset_x", "offset_y", "updated_at")
    list_filter = ("category", "media_profile", "is_default")
    search_fields = ("name",)
    inlines = [LabelFieldInline]


@admin.register(LabelPrintLog)
class LabelPrintLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "barcode", "quantity", "status", "template_name", "printer_name", "printed_by")
    list_filter = ("status", "created_at")
    search_fields = ("barcode", "template_name", "printer_name", "batch_id")
    readonly_fields = ("created_at", "updated_at", "batch_id")
    raw_id_fields = ("item", "template", "printed_by")
    date_hierarchy = "created_at"
