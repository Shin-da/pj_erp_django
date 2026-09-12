from django.contrib import admin

from .models import ApiClient


@admin.register(ApiClient)
class ApiClientAdmin(admin.ModelAdmin):
    list_display = ("name", "key_prefix", "is_active", "last_used_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "key_prefix")
    readonly_fields = ("key_prefix", "key_hash", "last_used_at", "created_at", "updated_at")

    def has_add_permission(self, request):
        # Raw keys can only be captured once, at creation — issue new
        # clients with `python manage.py create_api_client "<name>"`.
        return False
