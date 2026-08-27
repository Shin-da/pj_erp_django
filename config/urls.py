from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("products/", include("apps.catalogue.urls")),
    path("resellers/", include("apps.assignment.urls")),
    path("returns/", include("apps.returns.urls")),
    path("tracker/", include("apps.tracker.urls")),
    path("hardware/", include("apps.hardware.urls")),
    path("", include("apps.core.urls")),
]

# Migrated legacy PDFs and images live under MEDIA_ROOT. Django's dev
# server does not serve those by default, so wire it here — DEBUG only.
# In production the web server serves MEDIA_URL directly and this block
# does nothing, which is deliberate: `static()` returns an empty list when
# DEBUG is False rather than silently exposing the media tree through
# Django.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
