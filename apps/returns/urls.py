from django.urls import path

from . import views

app_name = "returns"

urlpatterns = [
    path("", views.return_scan, name="return_scan"),
    path("lookup/", views.item_lookup, name="item_lookup"),
    path("process/", views.process_returns, name="process_returns"),
]
