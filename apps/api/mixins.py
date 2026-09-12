from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated

from .authentication import ApiKeyAuthentication
from .pagination import StandardResultsSetPagination
from .permissions import HasDjangoPermission, IsEmployeeUser


class ApiClientReadMixin:
    """Every Phase 0/1 read endpoint: Api-Key only, authenticated, paginated."""

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination


class EmployeeWriteMixin:
    """Staff mutations: Employee session or DRF token — never Api-Key alone."""

    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated, IsEmployeeUser, HasDjangoPermission]
