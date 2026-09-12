"""
Returns and reservations.

Replaces `ProductReturn.aspx` + `tblreserved_master` / `tblreserved_items`
+ `reserve_itemmaster.aspx` / `reserve_alert_master.aspx`.

Legacy finding this fixes directly: reading `ProductReturn.aspx.cs::
btnSave_Click`, **every pending-soldstatus barcode was first run through
`return_product_by_barcode` regardless of the chosen outcome**, and only
*afterward* did `reassign()` or `reserve()` immediately re-claim it in the
same postback. So a "reserved" or "reassigned" item passed through
"returned" only as a transient, never-actually-queryable DB state — only a
plain return with no follow-up action left stock genuinely open
(INVENTORY-AND-INVOICING.md §7).

Modeled here as one real state-machine call per outcome
(`ReturnRecord.process()`), going straight from ASSIGNED to the intended
end state (PENDING for a plain return, RESERVED for a reserve, ASSIGNED
again for a reassignment) via `inventory.ProductItem.transition_status()`
— there is no intermediate "returned" state to accidentally observe or
rely on, because none of the three legacy outcomes actually left the item
sitting in one.

`sold_status='SOLD'`/`'sold'` casing inconsistency (§9a): irrelevant here
— `StockStatus` is an enum with a real Postgres CHECK constraint, so
there's no casing to get wrong.
"""

from django.conf import settings
from django.db import models, transaction

from apps.core.models import TimeStampedModel, AuditLogEntry
from apps.inventory.models import StockStatus


class ReturnOutcome(models.TextChoices):
    RETURN = "RETURN", "Plain return (back to open stock)"
    REASSIGN = "REASSIGN", "Reassign to same/another reseller"
    RESERVE = "RESERVE", "Move to reserve"
    SOLD = "SOLD", "Confirmed sold (not a return)"


class ReturnRecord(TimeStampedModel):
    item = models.ForeignKey("inventory.ProductItem", on_delete=models.PROTECT, related_name="return_records")
    assignment_line = models.ForeignKey(
        "assignment.AssignmentLine", null=True, blank=True, on_delete=models.SET_NULL, related_name="return_records"
    )
    outcome = models.CharField(max_length=20, choices=ReturnOutcome.choices)
    reassigned_to = models.ForeignKey(
        "assignment.Reseller", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="return_records"
    )

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            (
                "can_process_return",
                "Can process returns / reserve / confirm-sold",
            ),
        ]

    def __str__(self):
        return f"{self.get_outcome_display()}: {self.item.barcode}"

    @transaction.atomic
    def process(self):
        """
        One direct transition per outcome — no transient intermediate
        state. This is the structural fix for §7: there is nothing here
        equivalent to calling `return_product_by_barcode` unconditionally
        before deciding what actually happens next.
        """
        if self.outcome == ReturnOutcome.SOLD:
            self.item.transition_status(StockStatus.SOLD, actor=self.processed_by, reason="confirmed sold on return")
        elif self.outcome == ReturnOutcome.RESERVE:
            self.item.transition_status(StockStatus.RESERVED, actor=self.processed_by, reason="moved to reserve")
        elif self.outcome == ReturnOutcome.REASSIGN:
            # Stays ASSIGNED (possibly to a different reseller) — modeled
            # as a direct ASSIGNED->ASSIGNED-with-new-owner change at the
            # assignment layer, not a status transition here. Caller is
            # expected to create the new AssignmentLine separately via
            # AssignmentMaster.add_line(); this record is the audit trail.
            AuditLogEntry.record(
                actor=self.processed_by, action="return_reassigned", obj=self.item,
                summary=f"reassigned to {self.reassigned_to}" if self.reassigned_to else "reassigned",
            )
        else:  # RETURN
            self.item.transition_status(StockStatus.PENDING, actor=self.processed_by, reason="returned to open stock")


class ReserveAlert(TimeStampedModel):
    """
    Replaces `reserve_alert_master.aspx` / the reserve-expiry logic found
    in `sp_product_assign` (`update_reserve_re_days`). Legacy finding: no
    scheduled job anywhere calls that action — `Global.asax.cs` only
    starts the Tiara polling job — so reserves may not expire promptly
    unless some page happens to be visited (a finding from the full
    source read, not previously documented). `expires_at` here plus a
    real scheduled job (via `apps.sync`'s django-q cluster, once built) is
    the fix — don't rely on page-visit timing.
    """

    item = models.ForeignKey("inventory.ProductItem", on_delete=models.CASCADE, related_name="reserve_alerts")
    reseller = models.ForeignKey("assignment.Reseller", on_delete=models.PROTECT, related_name="reserve_alerts")
    expires_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["expires_at"]

    def __str__(self):
        return f"Reserve alert: {self.item.barcode} for {self.reseller} (expires {self.expires_at:%Y-%m-%d})"
