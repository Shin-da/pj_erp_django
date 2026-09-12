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


class SyncRun(models.Model):
    """
    One row per `sync_legacy_mssql` run.

    Every stock number in this system is a mirror of the live iadmin SQL
    Server, so "as of when" is part of the number. Without it the
    dashboard reads like a live shop floor when it is really a snapshot,
    and a sync that has been quietly failing for a week looks identical to
    one that ran a minute ago. The previous marker for this was a cache
    key, which does not survive a Render restart and is not shared between
    web workers.
    """

    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    ok = models.BooleanField(default=False)
    trigger = models.CharField(max_length=30, default="manual")
    summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        state = "ok" if self.ok else "failed"
        return f"Sync {self.started_at:%Y-%m-%d %H:%M} ({state})"

    @classmethod
    def last_success(cls):
        return cls.objects.filter(ok=True).order_by("-finished_at").first()


class LegacyDocumentKind(models.TextChoices):
    INVOICE_PDF = "INVOICE_PDF", "Generated invoice PDF"
    PAYMENT_PROOF = "PAYMENT_PROOF", "Proof of payment"
    LOCATION_LOGO = "LOCATION_LOGO", "Reseller-location logo"
    OTHER = "OTHER", "Other legacy file"


class LegacyDocument(TimeStampedModel):
    """
    A file produced by the old iadmin system, carried across so historical
    records stay viewable after that system is switched off.

    Generic in the same way `AuditLogEntry` is — `model_label` +
    `object_id` rather than a FK per attachable model — because the file
    types arrive in waves (invoice PDFs first, payment proofs next) and
    each wave would otherwise mean a schema change.

    Why copy rather than link to the legacy tree: the two systems live on
    different machines, and the legacy copy sits on unmanaged FTP hosting
    with no confirmed end date. A stored path would keep working right up
    until the moment it mattered.

    `sha256` and `source_path` exist so a migration can be *proved* rather
    than asserted — you can verify every file arrived intact before anyone
    deletes anything on the legacy side. Nothing in the app depends on
    them; they are there for the day someone asks.

    These are read-only artefacts. Nothing regenerates them, and the
    application must never write to this table outside the import command
    — a legacy PDF is evidence of what was printed at the time, not a
    live rendering of current data. If the underlying invoice is later
    corrected, the PDF will disagree with the screen, and the PDF is the
    one that was handed to the customer.
    """

    model_label = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=64, db_index=True)
    kind = models.CharField(
        max_length=20, choices=LegacyDocumentKind.choices, default=LegacyDocumentKind.OTHER, db_index=True
    )
    file = models.FileField(upload_to="legacy/%Y/%m/")
    original_name = models.CharField(max_length=255)
    source_path = models.CharField(
        max_length=500, blank=True, help_text="Where this came from in the legacy tree, for audit."
    )
    byte_size = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["model_label", "object_id", "kind"]),
        ]
        constraints = [
            # Re-running the import must not duplicate a file. Same content
            # attached to the same record once, however many times the
            # command is run.
            models.UniqueConstraint(
                fields=["model_label", "object_id", "sha256"],
                name="unique_legacy_document_per_object",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.original_name}"

    @classmethod
    def for_object(cls, obj, kind=None):
        qs = cls.objects.filter(
            model_label=f"{obj._meta.app_label}.{obj._meta.model_name}", object_id=str(obj.pk)
        )
        return qs.filter(kind=kind) if kind else qs
