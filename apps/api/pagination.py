from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """Default list page size with a hard ceiling clients cannot bypass."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
