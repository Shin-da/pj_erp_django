from django.contrib import admin

from .models import Transfer


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = ("id", "from_location", "to_location", "status", "created_by", "created_at")
    list_filter = ("status", "from_location", "to_location")
