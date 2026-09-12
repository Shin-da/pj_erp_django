from rest_framework.permissions import IsAuthenticated

from .authentication import ApiKeyAuthentication
from .pagination import StandardResultsSetPagination


class ApiClientReadMixin:
    """Every Phase 0/1 read endpoint: Api-Key only, authenticated, paginated."""

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
