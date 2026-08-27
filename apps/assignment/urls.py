from django.urls import path

from . import views

app_name = "assignment"

urlpatterns = [
    path("", views.group_list, name="group_list"),
    path("group/<int:pk>/", views.group_detail, name="group_detail"),
    path("client/<int:pk>/", views.client_detail, name="client_detail"),
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("invoices/create/", views.invoice_create, name="invoice_create"),
    path("invoices/item-lookup/", views.item_lookup, name="item_lookup"),
    path("invoices/<int:pk>/", views.invoice_list, name="invoice_detail"),
    path("invoices/<int:pk>/stamp/", views.invoice_stamp, name="invoice_stamp"),
    path("invoices/<int:pk>/pdf/", views.invoice_pdf, name="invoice_pdf"),
    path("invoices/<int:pk>/preview/", views.invoice_pdf_preview, name="invoice_pdf_preview"),
]
