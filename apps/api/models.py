"""
Access control for the external-facing read API — deliberately not the
same identity as `accounts.Employee`. An external developer's system
authenticates as an `ApiClient`, never as a staff login: a leaked API key
should not be a path into Django admin, and revoking a client's access
should never touch anyone's actual employee account.

Only a hash of the key is stored (sha256, unsalted — the key itself is
high-entropy random, not a user-chosen password, so a salt buys nothing
here). The raw key is shown exactly once, at creation, by
`create_api_client`; there is no way to recover it afterwards, only to
issue a new one.
"""

import hashlib
import secrets

from django.db import models

from apps.core.models import TimeStampedModel


def _generate_raw_key() -> str:
    return secrets.token_urlsafe(32)


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class ApiClient(TimeStampedModel):
    name = models.CharField(
        max_length=150,
        help_text="Who/what holds this key — e.g. the external developer's system name.",
    )
    key_prefix = models.CharField(
        max_length=12,
        unique=True,
        editable=False,
        help_text="First characters of the key, shown alongside the client for identification. Not a secret on its own.",
    )
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.key_prefix}…)"

    # DRF's IsAuthenticated checks request.user.is_authenticated — this
    # stands in for a User here, so it needs to answer that.
    @property
    def is_authenticated(self) -> bool:
        return True

    @classmethod
    def create_with_key(cls, name: str, notes: str = "") -> tuple["ApiClient", str]:
        """Returns (client, raw_key). raw_key is never stored — capture it now."""
        raw_key = _generate_raw_key()
        client = cls.objects.create(
            name=name,
            key_prefix=raw_key[:8],
            key_hash=hash_key(raw_key),
            notes=notes,
        )
        return client, raw_key
