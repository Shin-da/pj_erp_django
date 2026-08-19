from django.contrib import admin

from .models import ResellerPayment, SupplierPayment, InvoiceCancellation


@admin.register(ResellerPayment)
class ResellerPaymentAdmin(admin.ModelAdmin):
    list_display = ("assignment", "amount", "paid_on", "recorded_by")
    autocomplete_fields = ("assignment",)


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = ("supplier", "product", "amount", "paid_on", "recorded_by")
    autocomplete_fields = ("supplier", "product")


@admin.register(InvoiceCancellation)
class InvoiceCancellationAdmin(admin.ModelAdmin):
    list_display = ("assignment", "approved", "requested_by", "approved_by", "created_at")
    autocomplete_fields = ("assignment",)
