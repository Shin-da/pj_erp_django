from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("locations/", views.location_list, name="location_list"),
    path("locations/<str:code>/", views.location_detail, name="location_detail"),
]
