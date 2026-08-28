from django.urls import path

from . import search as search_views
from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", search_views.search, name="search"),
    path("search/suggest/", search_views.search_suggest, name="search_suggest"),
    path("internal/sync-legacy-mssql/", views.sync_legacy_webhook, name="sync_legacy_webhook"),
]
