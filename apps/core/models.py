"""
Shared base models.

The legacy `stock_rfid` schema has none of this anywhere: no created_at/
updated_at on any of its 72 tables, no consistent soft-delete (some tables
use `bstatus`, some don't, and at least one procedure — `deallocate_room` —
sets `bstatus=1` to mean *active* while everywhere else in the same schema
`bstatus=1` means *not deleted*, i.e. the flag is used inconsistently even
within one meaning), and no durable audit trail (DATA-FLOW-VERIFICATION.md
confirmed the tracker "audit log" in the old app is appended to ViewState
only — it does not survive the request). This app exists so every other
app gets these for free and consistently.
"""

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """created_at / updated_at on every table, always in the same shape."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def inactive(self):
        return self.filter(is_active=False)


class ActiveManager(models.Manager):
    """Default manager — only returns non-deleted rows."""

    def get_queryset(self):
        return ActiveQuerySet(self.model, using=self._db).filter(is_active=True)


class SoftDeleteModel(TimeStampedModel):
    """
    One soft-delete flag, one meaning, everywhere: `is_active=True` means
    the row is live. No second `active_status` field with independent,
    inconsistently-applied semantics (see the legacy `tblcompany_locations`
    finding in INVENTORY-AND-INVOICING.md §2 — `bstatus` and
    `active_status` disagreeing on what "usable" means was a real,
    documented bug source there).
    """

    is_active = models.BooleanField(default=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self):
        from django.utils import timezone

        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_active", "deleted_at"])

    def restore(self):
        self.is_active = True
        self.deleted_at = None
        self.save(update_fields=["is_active", "deleted_at"])


class AuditLogEntry(models.Model):
    """
    A real, persistent, queryable audit trail — replacing the legacy
    system's ViewState-only tracker log (never written to a table) and the
    ad-hoc `tblsitelog` (4,136 rows at last audit, but not consistently
    written to by every mutating action).

    Generic by design: any model can write an entry here via
    `AuditLogEntry.record(...)` without a schema change. Keep writes to
    genuinely significant state transitions (stock status changes,
    invoice stamping, transfers, cancellations) — not a log of every
    field edit.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=100, db_index=True)
    model_label = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=64, db_index=True)
    summary = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["model_label", "object_id"]),
        ]

    def __str__(self):
        return f"{self.action} on {self.model_label}#{self.object_id} at {self.created_at:%Y-%m-%d %H:%M}"

    @classmethod
    def record(cls, *, actor, action, obj, summary="", changes=None):
        return cls.objects.create(
            actor=actor,
            action=action,
            model_label=f"{obj._meta.app_label}.{obj._meta.model_name}",
            object_id=str(obj.pk),
            summary=summary,
            changes=changes or {},
        )
