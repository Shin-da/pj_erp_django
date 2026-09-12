from django.contrib import admin

from .models import TrackerSession, TrackerScanItem


class TrackerScanItemInline(admin.TabularInline):
    model = TrackerScanItem
    extra = 0
    autocomplete_fields = ("item", "location_at_scan")


@admin.register(TrackerSession)
class TrackerSessionAdmin(admin.ModelAdmin):
    list_display = ("scan_index", "mode", "location", "item_count", "created_by", "created_at")
    list_filter = ("mode", "location", "is_transfer")
    inlines = [TrackerScanItemInline]
