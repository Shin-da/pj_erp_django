from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Employee


@admin.register(Employee)
class EmployeeAdmin(UserAdmin):
    model = Employee
    ordering = ["employee_code"]
    list_display = ("employee_code", "first_name", "last_name", "is_developer", "is_staff", "is_active", "default_location")
    search_fields = ("employee_code", "first_name", "last_name", "email")
    fieldsets = (
        (None, {"fields": ("employee_code", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email", "default_location")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "is_developer", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login",)}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("employee_code", "password1", "password2", "is_staff", "is_active"),
        }),
    )
