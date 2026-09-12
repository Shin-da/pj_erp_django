from django.contrib import admin

from .models import AuditLogEntry, LegacyDocument


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "model_label", "object_id", "summary")
    list_filter = ("action", "model_label")
    search_fields = ("object_id", "summary")
    readonly_fields = [f.name for f in AuditLogEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(LegacyDocument)
class LegacyDocumentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "kind", "model_label", "object_id", "byte_size", "created_at")
    list_filter = ("kind", "model_label")
    search_fields = ("original_name", "object_id", "sha256")
    readonly_fields = [f.name for f in LegacyDocument._meta.fields]

    def has_add_permission(self, request):
        # These arrive only through `import_legacy_documents`. A legacy
        # PDF is evidence of what was printed at the time — hand-adding
        # one here would make that claim untrue.
        return False

    def has_change_permission(self, request, obj=None):
        return False
