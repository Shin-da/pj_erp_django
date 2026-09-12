from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import ApiClient, hash_key

KEYWORD = "Api-Key"


class ApiKeyAuthentication(BaseAuthentication):
    """
    ``Authorization: Api-Key <raw key>``. Returns an ApiClient as
    request.user (never an Employee — see models.py) and None for
    request.auth; there are no per-request scopes yet, only active/revoked.
    """

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith(f"{KEYWORD} "):
            return None

        raw_key = header[len(KEYWORD) + 1:].strip()
        if not raw_key:
            raise AuthenticationFailed("Empty API key.")

        try:
            client = ApiClient.objects.get(key_hash=hash_key(raw_key), is_active=True)
        except ApiClient.DoesNotExist:
            raise AuthenticationFailed("Invalid or revoked API key.")

        ApiClient.objects.filter(pk=client.pk).update(last_used_at=timezone.now())
        return (client, None)

    def authenticate_header(self, request):
        return KEYWORD
