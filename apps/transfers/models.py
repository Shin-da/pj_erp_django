"""
Location-to-location transfers.

Replaces `ProductTransfer.aspx` / `ProductTransferList.aspx` +
`sp_product_transfer_management` + `tblproduct_transfer` /
`tblproduct_transfer_details`.

Legacy findings this fixes:
  - `update_product_location` (the SP action) only ever wrote
    `tblproduct_master.company_locationid` — the shared design record —
    which is why one barcode's transfer could silently relocate every
    sibling barcode on the same master (§9a.1/§9b.3). Here,
    `Transfer.execute()` calls `ProductItem.move_to_location()` per line,
    which only ever touches that one physical item — there's no shared
    master-level location to accidentally drag along.
  - `tblproduct_transfer_details.tranfer_id` was a misspelled column name,
    kept because "load-bearing" (INVENTORY-AND-INVOICING.md §4). No reason
    to carry the typo forward here.
  - **Return-transfer was unimplemented**: `btnreturn_Click` in
    `ProductTransferList.aspx.cs` was entirely commented out behind a live
    button, and no stored procedure action ever set
    `tblproduct_transfer.return_status` (confirmed by reading every
    procedure body — INVENTORY-AND-INVOICING.md §4.5, §10 item 3). This
    was a genuinely missing feature, not a legacy behavior to preserve.
    `Transfer.execute_return()` here actually implements it: moves every
    line's item back to `from_location` and marks the transfer
    `RETURNED`.
  - From/destination routing (`InventoryLocationHelper.BindToLocationDropdown`):
    From HO -> any other active location; from a branch -> any other
    active location including HO, excluding self. Branch-to-branch is
    allowed (confirmed as the active-sync behavior, superseding an older
    hub-and-spoke-only design). `Transfer.clean()` enforces the same rule.
  - Location-match validation: `ProductTransfer.bindgrid()` /
    `btntransfer_Click` stripped/blocked barcodes whose effective location
    didn't match the selected From location before writing anything.
    `Transfer.execute()` does the same check before moving anything, and
    raises rather than silently dropping mismatched lines.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.core.models import TimeStampedModel, AuditLogEntry


class TransferStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    COMPLETE = "COMPLETE", "Complete"
    RETURNED = "RETURNED", "Returned"


class TransferLocationMismatch(Exception):
    """Raised when a line's item isn't actually at the transfer's from_location."""


class Transfer(TimeStampedModel):
    legacy_id = models.IntegerField(
        null=True, blank=True, unique=True, db_index=True,
        help_text="tblproduct_transfer.nid — lets a re-sync from iadmin update this exact transfer instead of duplicating it.",
    )
    from_location = models.ForeignKey(
        "locations.Location", on_delete=models.PROTECT, related_name="transfers_out"
    )
    to_location = models.ForeignKey(
        "locations.Location", on_delete=models.PROTECT, related_name="transfers_in"
    )
    status = models.CharField(max_length=20, choices=TransferStatus.choices, default=TransferStatus.PENDING)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="transfers_created"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Transfer #{self.pk}: {self.from_location.code} -> {self.to_location.code}"

    def clean(self):
        if self.from_location_id and self.to_location_id and self.from_location_id == self.to_location_id:
            raise ValidationError("from_location and to_location must differ.")

    @transaction.atomic
    def execute(self, *, actor=None):
        """
        Moves every line's item from_location -> to_location. Validates
        every line is actually at from_location *before* moving anything
        — the legacy page validated per-line and silently stripped
        mismatches; here a mismatch aborts the whole transfer rather than
        partially executing it.
        """
        if self.status != TransferStatus.PENDING:
            raise ValueError(f"Transfer #{self.pk} is not pending (status={self.status}).")

        lines = list(self.lines.select_related("item").all())
        mismatched = [l.item.barcode for l in lines if l.item.location_id != self.from_location_id]
        if mismatched:
            raise TransferLocationMismatch(
                f"{len(mismatched)} item(s) not at {self.from_location.code}: {', '.join(mismatched)}"
            )

        for line in lines:
            line.item.move_to_location(self.to_location, actor=actor, transfer=self)

        self.status = TransferStatus.COMPLETE
        self.save(update_fields=["status", "updated_at"])
        AuditLogEntry.record(
            actor=actor, action="transfer_executed", obj=self,
            summary=f"{len(lines)} item(s) {self.from_location.code} -> {self.to_location.code}",
        )

    @transaction.atomic
    def execute_return(self, *, actor=None):
        """
        The feature the legacy system never finished (§4.5): move every
        line's item back to from_location and mark the transfer RETURNED.
        Only valid from COMPLETE — there's nothing to return from PENDING.
        """
        if self.status != TransferStatus.COMPLETE:
            raise ValueError(f"Transfer #{self.pk} must be COMPLETE to return (status={self.status}).")

        for line in self.lines.select_related("item").all():
            line.item.move_to_location(self.from_location, actor=actor, transfer=self)

        self.status = TransferStatus.RETURNED
        self.save(update_fields=["status", "updated_at"])
        AuditLogEntry.record(
            actor=actor, action="transfer_returned", obj=self,
            summary=f"{self.lines.count()} item(s) returned to {self.from_location.code}",
        )


class TransferLine(TimeStampedModel):
    transfer = models.ForeignKey(Transfer, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("inventory.ProductItem", on_delete=models.PROTECT, related_name="transfer_lines")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["transfer", "item"], name="unique_item_per_transfer"),
        ]

    def __str__(self):
        return f"{self.item.barcode} on {self.transfer}"
