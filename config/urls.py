from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("products/", include("apps.catalogue.urls")),
    path("resellers/", include("apps.assignment.urls")),
    path("tracker/", include("apps.tracker.urls")),
    path("hardware/", include("apps.hardware.urls")),
    path("", include("apps.core.urls")),
]
