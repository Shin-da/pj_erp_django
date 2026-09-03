from django.contrib import admin

from .models import LabelField, LabelTemplate


class LabelFieldInline(admin.TabularInline):
    model = LabelField
    extra = 0


@admin.register(LabelTemplate)
class LabelTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "media_profile", "is_default", "width_dots", "height_dots", "updated_at")
    list_filter = ("category", "media_profile", "is_default")
    search_fields = ("name",)
    inlines = [LabelFieldInline]
