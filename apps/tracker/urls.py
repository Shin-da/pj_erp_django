from django.urls import path

from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.scan, name="scan"),
    path("validate/", views.validate_barcodes, name="validate_barcodes"),
    path("expected-count/", views.expected_count, name="expected_count"),
    path("preview/", views.scan_preview, name="scan_preview"),
]
