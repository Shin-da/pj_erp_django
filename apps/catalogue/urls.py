from django.urls import path

from . import views

app_name = "catalogue"

urlpatterns = [
    path("", views.product_list, name="product_list"),
    path("item/<str:barcode>/", views.item_detail, name="item_detail"),
    path("<int:pk>/", views.product_detail, name="product_detail"),
]
