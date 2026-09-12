from rest_framework.permissions import BasePermission

from apps.api.models import ApiClient


class IsEmployeeUser(BasePermission):
    """Reject ApiClient keys — write ops require a real Employee."""

    message = "Employee authentication required."

    def has_permission(self, request, view):
        user = request.user
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if isinstance(user, ApiClient):
            return False
        return hasattr(user, "employee_code")


class HasDjangoPermission(BasePermission):
    """
    Checks ``view.required_permission`` (e.g. ``returns.can_process_return``).
    Superusers always pass.
    """

    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        codename = getattr(view, "required_permission", None)
        if not codename:
            return False
        user = request.user
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if isinstance(user, ApiClient):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return user.has_perm(codename)
