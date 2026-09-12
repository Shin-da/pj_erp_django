from django.urls import path

from . import views

app_name = "catalogue"

urlpatterns = [
    path("", views.product_list, name="product_list"),
    path("add/", views.product_intake, name="product_intake"),
    path("add/template/", views.intake_template, name="intake_template"),
    path("add/history/<int:pk>/", views.intake_batch_detail, name="intake_batch"),
    path("add/history/<int:pk>/file/", views.intake_batch_file, name="intake_batch_file"),
    path("photos/", views.product_photo_upload, name="photo_upload"),
    path("item/<str:barcode>/", views.item_detail, name="item_detail"),
    path("<int:pk>/", views.product_detail, name="product_detail"),
]
