from django.contrib.auth.views import LoginView, LogoutView


class EmployeeLoginView(LoginView):
    """
    Login is by `employee_code` (see AUTH_USER_MODEL / Employee.USERNAME_FIELD),
    not a separate username — replaces `login.aspx` -> `sp_getadminbyusernamepass`.
    """

    template_name = "accounts/login.html"


class EmployeeLogoutView(LogoutView):
    pass
