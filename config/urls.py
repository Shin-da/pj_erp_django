from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.api.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("products/", include("apps.catalogue.urls")),
    path("resellers/", include("apps.assignment.urls")),
    path("returns/", include("apps.returns.urls")),
    path("tracker/", include("apps.tracker.urls")),
    path("hardware/", include("apps.hardware.urls")),
    path("", include("apps.core.urls")),
]

# Product photos / reseller logos / legacy PDFs. Prefer S3/R2
# (USE_S3_MEDIA) so gunicorn never serves the tree. When media is still
# on local disk (dev, or Render + persistent disk), SERVE_MEDIA wires
# Django's serve view — WhiteNoise does not cover uploads.
# Note: django.conf.urls.static.static() is a no-op when DEBUG=False,
# so we call serve directly.
if settings.SERVE_MEDIA and not settings.USE_S3_MEDIA:
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
