from django.urls import path

from . import views

app_name = "hardware"

urlpatterns = [
    path("templates/", views.template_list, name="template_list"),
    path("templates/new/", views.template_create, name="template_create"),
    path("templates/<int:pk>/", views.template_edit, name="template_edit"),
    path("templates/<int:pk>/save/", views.template_save, name="template_save"),
    path("templates/<int:pk>/duplicate/", views.template_duplicate, name="template_duplicate"),
    path("templates/<int:pk>/delete/", views.template_delete, name="template_delete"),
    path("print/", views.print_labels, name="print_labels"),
]
