from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.EmployeeLoginView.as_view(), name="login"),
    path("logout/", views.EmployeeLogoutView.as_view(), name="logout"),
]
