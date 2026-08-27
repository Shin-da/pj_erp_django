from django.contrib import admin

from .models import Location


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "location_type", "is_active")
    list_filter = ("location_type", "is_active")
    search_fields = ("code", "name")
