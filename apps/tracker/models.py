"""
Stocktake / scan tracking.

Replaces `tblproduct_tracker` + `tblproduct_tracker_itemsdeatils` +
`product_tracker.aspx`'s multimode logic (opening / closing / check /
transfer).

Per REBUILD-ARCHITECTURE-AND-BUDGET.md §2, this app and `inventory` were
identified as the lowest-risk starting point: the opening/closing/check
workflow was already redesigned once in the legacy `active-sync` branch
(location-scoped scans, snapshot-based reconciliation) — that redesign is
the blueprint here, not wasted work.

Legacy findings this fixes:
  - `tblproduct_tracker.parent_tracker_ids` links a closing scan back to
    the opening scan(s) it closes via a delimited string column
    (confirmed in SCAN-TRANSFER-WORKFLOW.md §2 and the C# read path) —
    here it's a real self-referencing FK.
  - The "audit trail" for a tracker session lived only in ViewState
    (DATA-FLOW-VERIFICATION.md, final section) — never persisted. Every
    `TrackerSession`/`TrackerScanItem` write here is a real row, and
    significant transitions also go through `core.AuditLogEntry`.
"""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class ScanMode(models.TextChoices):
    OPENING = "OPENING", "Opening count"
    CLOSING = "CLOSING", "Closing count"
    CHECK = "CHECK", "Check item"


class ScanResult(models.TextChoices):
    COMPANY_STOCK = "COMPANY_STOCK", "Company stock"
    ASSIGNED = "ASSIGNED", "Assigned"
    SOLD = "SOLD", "Sold"
    RESERVED = "RESERVED", "Reserved"
    LOSS = "LOSS", "Loss"
    ELSEWHERE = "ELSEWHERE", "Elsewhere"
    WRONG_LOCATION = "WRONG_LOCATION", "Wrong location"
    NOT_FOUND = "NOT_FOUND", "Not found"


class TrackerSession(TimeStampedModel):
    scan_index = models.PositiveIntegerField(unique=True, editable=False)
    location = models.ForeignKey(
        "locations.Location", on_delete=models.PROTECT, related_name="tracker_sessions"
    )
    mode = models.CharField(max_length=10, choices=ScanMode.choices)
    parent_session = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="closing_sessions",
        help_text="For a CLOSING session, the OPENING session(s) it closes out.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="tracker_sessions"
    )
    item_count = models.PositiveIntegerField(default=0)
    is_transfer = models.BooleanField(default=False)
    transfer = models.ForeignKey(
        "transfers.Transfer", null=True, blank=True, on_delete=models.SET_NULL, related_name="tracker_sessions"
    )

    class Meta:
        ordering = ["-scan_index"]

    def __str__(self):
        return f"SN{self.scan_index:03d} ({self.mode} @ {self.location.code})"

    def save(self, *args, **kwargs):
        if self.scan_index is None:
            last = TrackerSession.objects.order_by("-scan_index").first()
            self.scan_index = (last.scan_index + 1) if last else 1
        super().save(*args, **kwargs)


class TrackerScanItem(TimeStampedModel):
    session = models.ForeignKey(TrackerSession, on_delete=models.CASCADE, related_name="scan_items")
    item = models.ForeignKey("inventory.ProductItem", on_delete=models.PROTECT, related_name="tracker_scans")
    result = models.CharField(max_length=20, choices=ScanResult.choices, blank=True)
    location_at_scan = models.ForeignKey(
        "locations.Location", null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["session", "item__barcode"]
        constraints = [
            models.UniqueConstraint(fields=["session", "item"], name="unique_item_per_session"),
        ]

    def __str__(self):
        return f"{self.item.barcode} in {self.session}"
