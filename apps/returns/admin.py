from django.contrib import admin

from .models import ReturnRecord, ReserveAlert


@admin.register(ReturnRecord)
class ReturnRecordAdmin(admin.ModelAdmin):
    list_display = ("item", "outcome", "reassigned_to", "processed_by", "created_at")
    list_filter = ("outcome",)
    autocomplete_fields = ("item", "assignment_line", "reassigned_to")


@admin.register(ReserveAlert)
class ReserveAlertAdmin(admin.ModelAdmin):
    list_display = ("item", "reseller", "expires_at", "resolved_at")
    list_filter = ("resolved_at",)
    autocomplete_fields = ("item", "reseller")
