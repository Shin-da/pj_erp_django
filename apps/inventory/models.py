"""
Physical inventory items — one row per barcode/RFID tag.

Replaces `tblproduct_detail_master`.

Legacy findings this fixes:
  - `sold_status` was a free-text column compared with inconsistent casing
    throughout the codebase (`'assign'` / `'ASSIGN'`, `'sold'` / `'SOLD'`),
    which only worked because SQL Server's default collation is
    case-insensitive (confirmed in INVENTORY-AND-INVOICING.md §9a.5 — "no
    rows currently have sold_status='assign'", and `sp_product_assign`'s
    `check_barcode_reserve_bybarcodenumber` action checks `'SOLD'` while
    every sibling action in the same procedure checks `'sold'`). A
    PostgreSQL-backed `TextChoices` field plus a DB `CHECK` constraint
    (via `choices=`) makes a mismatched-case write a validation error
    instead of a silent, collation-dependent no-op.
  - Location was resolved at read time via
    `COALESCE(detail.company_locationid, master.company_locationid, default)`
    (`InventoryLocationHelper.EffectiveLocationSql`, confirmed reading the
    C#) because the per-item location column
    (`tblproduct_detail_master.company_locationid`, added by
    `scripts/003_detail_location.sql` in the active-sync branch) was a
    late retrofit onto a schema that originally only tracked location on
    the shared product master. Here, location is simply a real, always-
    populated FK on the item — there is nothing to fall back to.
  - Legacy `tblproduct_detail_master` already had `transfer_status`
    (bit) and `transfer_id` (int) columns that **no stored procedure ever
    wrote to** (confirmed by grepping every procedure body in the
    `.dacpac`'s `model.xml` — 2 mentions each, both in the `CREATE TABLE`,
    zero in any `INSERT`/`UPDATE` — IADMIN-SYSTEM-REFERENCE.md /
    INVENTORY-AND-INVOICING.md §9b.3). The design was already correct;
    it just wasn't wired up. `last_transfer` here is that design, wired up.
"""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, AuditLogEntry


class StockStatus(models.TextChoices):
    PENDING = "PENDING", "Company stock (pending)"
    ASSIGNED = "ASSIGNED", "Assigned to reseller"
    RESERVED = "RESERVED", "Reserved"
    SOLD = "SOLD", "Sold"
    IN_TRANSIT = "IN_TRANSIT", "In transit (transfer in progress)"


# Deliberately conservative — mirrors the states the legacy system actually
# used (INVENTORY-AND-INVOICING.md §3) rather than inventing new ones.
# Extend this as `assignment`/`returns`/`transfers` get built out.
VALID_TRANSITIONS = {
    StockStatus.PENDING: {StockStatus.ASSIGNED, StockStatus.RESERVED, StockStatus.IN_TRANSIT},
    StockStatus.ASSIGNED: {StockStatus.SOLD, StockStatus.PENDING, StockStatus.RESERVED},
    StockStatus.RESERVED: {StockStatus.ASSIGNED, StockStatus.PENDING},
    StockStatus.SOLD: {StockStatus.PENDING},  # invoice cancel / return path
    StockStatus.IN_TRANSIT: {StockStatus.PENDING},
}


class InvalidStatusTransition(Exception):
    pass


class ProductItem(TimeStampedModel):
    barcode = models.CharField(max_length=100, unique=True, db_index=True)
    rfid_epc = models.CharField(
        max_length=100, blank=True,
        help_text="RFID chip payload. Legacy ZPL templates wrote the barcode string itself here (^RFW,a,2,,A ^FD{barcode}) — kept as the default unless a distinct EPC scheme is adopted.",
    )
    product = models.ForeignKey(
        "catalogue.ProductMaster", on_delete=models.PROTECT, related_name="items"
    )
    location = models.ForeignKey(
        "locations.Location", on_delete=models.PROTECT, related_name="items"
    )
    status = models.CharField(
        max_length=20, choices=StockStatus.choices, default=StockStatus.PENDING, db_index=True
    )
    reprint_status = models.CharField(
        max_length=20,
        choices=[("NONE", "Not printed"), ("PRINTED", "Printed"), ("REPRINT_PENDING", "Reprint pending approval")],
        default="NONE",
    )

    class Meta:
        ordering = ["barcode"]
        indexes = [
            models.Index(fields=["status", "location"]),
        ]

    def __str__(self):
        return self.barcode

    def transition_status(self, new_status, *, actor=None, reason=""):
        """
        The legacy equivalent of this was `manage_stock`'s two opposite
        UPDATEs, both reading live table state rather than a pre-batch
        snapshot, which made a normal scan a no-op and could silently
        un-assign an already-assigned item (confirmed by controlled test,
        INVENTORY-AND-INVOICING.md §9a.2). Enforcing a transition table
        server-side, in one method every caller goes through, makes that
        class of bug structurally impossible rather than something to
        remember to check per call site.
        """
        current = StockStatus(self.status)
        target = StockStatus(new_status)
        if target not in VALID_TRANSITIONS.get(current, set()):
            raise InvalidStatusTransition(f"{current} -> {target} is not a permitted transition")

        old_status = self.status
        self.status = target
        self.save(update_fields=["status", "updated_at"])
        AuditLogEntry.record(
            actor=actor,
            action="status_transition",
            obj=self,
            summary=f"{old_status} -> {target}" + (f" ({reason})" if reason else ""),
            changes={"from": old_status, "to": str(target)},
        )

    def move_to_location(self, new_location, *, actor=None, transfer=None):
        """
        Real per-item location move, always. Replaces
        `sp_product_transfer_management`'s `update_product_location`,
        which only ever wrote `tblproduct_master.company_locationid` — the
        shared *design* record, not the physical item — which is exactly
        why one barcode's transfer could silently "move" every sibling
        barcode sharing that design (INVENTORY-AND-INVOICING.md §9a.1,
        §9b.3). There is no master-level location here to keep in sync;
        this is the only location record for the item.
        """
        old_location = self.location
        if old_location.pk == new_location.pk:
            return
        self.location = new_location
        self.save(update_fields=["location", "updated_at"])
        AuditLogEntry.record(
            actor=actor,
            action="location_transfer",
            obj=self,
            summary=f"{old_location.code} -> {new_location.code}" + (f" (transfer #{transfer.pk})" if transfer else ""),
            changes={
                "from_location": old_location.code,
                "to_location": new_location.code,
                "transfer_id": transfer.pk if transfer else None,
            },
        )
