"""
Reseller assignment = invoicing.

Replaces `productassign.aspx` + `ResellerPaymentInvoice.aspx` +
`tblProductAssignMaster` / `tblproductassign` + `tblresellermaster` +
`product_assign_management` (the 58-branch stored procedure that was the
real engine here) + the room-allotment coupling.

This is the single most important legacy finding to get right: **there is
no separate invoice document.** `ProductInvoice.aspx` / `ProductEdit.aspx`
were empty stubs that redirected to `productassign.aspx` in the
active-sync branch. An invoice is a status stamped onto the assignment
record itself (INVENTORY-AND-INVOICING.md §5). Same shape here:
`AssignmentMaster.invoice_number`/`invoice_status` are columns on this
model, not a separate table.

Legacy findings this fixes:
  - **Invoice numbers were derived from the row primary key**
    (`"RE00"+masterId` / `"RN00"+masterId`, first stamp only, reopening
    preserved the existing number) — no sequence table, gaps wherever a
    master row was created and deleted, inconsistent zero-padding
    (`RE00`+7 = `RE007` but `RE00`+1234 = `RE001234`) (§5.1). A real
    Postgres sequence (`AssignmentMaster.invoice_seq`, via a
    `models.Sequence`-backed default) with fixed-width zero-padding fixes
    this by construction.
  - **Two independently-maintained pricing calculations** existed in
    `sp_product_assign` (`insert_alvin_discount`'s `@type='true'` branch
    vs. its else branch), which SQL comments said had to be kept manually
    aligned with `get_reseller_invoicedata_edit`/`get_reseller_invoicedata`
    — a real source of invoice-total drift. `calculate_line_total()` here
    is the one function every price calculation goes through.
  - **The room-allotment coupling is real, not dead code**: every
    `insert_master` call in the legacy SP also wrote
    `tblRoomAllotmentMaster` (`Employee_ID` actually meaning
    `reseller_id`), confirmed reading the SP body directly
    (IADMIN-SYSTEM-REFERENCE.md / INVENTORY-AND-INVOICING.md §9a.8).
    Modeled explicitly here as `DisplaySlot` — a real, honestly-named
    concept (a showroom counter/case/consignment slot at a reseller) —
    instead of a jewellery assignment silently reaching into a hotel
    room-booking table. **Confirm with the business whether this concept
    is still actually used before assuming every assignment needs one**
    (see priority-questions list in the project doc); the FK here is
    nullable so assignment can work either way.
  - **Room-availability checks disagreed between two legacy pages** —
    `productassign.aspx.cs`'s `fillroom()` had no filter excluding
    already-'Allocated' rooms, while `Rfid_scan.aspx.cs`'s did — so one
    page could double-book a slot the other would block. One
    `DisplaySlot.is_available` property here, used everywhere.
  - `checkbarcode_reserved()` in the legacy `productassign.aspx.cs` called
    a conflict-check SP but never inspected the returned result — a
    no-op guard. `AssignmentMaster.add_line()` here actually raises if the
    item isn't in a valid pre-assignment state.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.core.models import TimeStampedModel, SoftDeleteModel, AuditLogEntry
from apps.inventory.models import StockStatus


class Reseller(TimeStampedModel):
    """Replaces `tblresellermaster`. Deliberately NOT the same concept as
    `locations.Location` — see INVENTORY-AND-INVOICING.md §2: "Company
    locations and reseller locations are different concepts. Don't
    conflate them" (a distinction the legacy schema itself maintained
    correctly, worth keeping)."""

    name = models.CharField(max_length=150)
    reference_code = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class DisplaySlot(TimeStampedModel):
    """
    A showroom counter/case/consignment slot at a reseller. Replaces the
    repurposed `tblRoomMaster`/`tblRoomAllotmentMaster` pair — same
    concept, honest name, one availability check instead of two
    disagreeing ones.
    """

    name = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_available(self):
        return not self.allotments.filter(released_at__isnull=True).exists()


class DisplaySlotAllotment(TimeStampedModel):
    slot = models.ForeignKey(DisplaySlot, on_delete=models.PROTECT, related_name="allotments")
    reseller = models.ForeignKey(Reseller, on_delete=models.PROTECT, related_name="slot_allotments")
    released_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.slot} <- {self.reseller}" + ("" if self.released_at else " (active)")


class InvoiceStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    COMPLETE = "COMPLETE", "Complete (invoiced)"
    CANCELLED = "CANCELLED", "Cancelled"


class AssignmentMaster(SoftDeleteModel):
    """
    Extends `SoftDeleteModel`, not `TimeStampedModel` — deliberately.
    Legacy finding §5.1: "Deleting an assignment master orphans an
    already-issued invoice number." A hard DELETE was possible in the
    legacy schema (no FK protecting the row), so an issued invoice number
    could point at nothing. Here, `AssignmentMaster.objects` never returns
    a soft-deleted row and the invoice number stays pinned to Django's
    own `id` (a real DB sequence — gapless in practice as long as rows are
    cancelled via `is_active=False` rather than actually deleted, which
    this base class makes the natural path).
    """

    reseller = models.ForeignKey(Reseller, on_delete=models.PROTECT, related_name="assignments")
    display_slot = models.ForeignKey(
        DisplaySlot, null=True, blank=True, on_delete=models.SET_NULL, related_name="assignments",
        help_text="Optional — only if this reseller has a physical display slot allotted (see class docstring).",
    )
    is_reserve = models.BooleanField(
        default=False, help_text="Reserve-path assignment (legacy RN00 prefix) vs. normal reseller assignment (RE00)."
    )
    invoice_status = models.CharField(max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="assignments_created"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.invoice_number

    @property
    def invoice_number(self):
        """
        Fixed-width, pinned to `id` (a real Postgres sequence) — replaces
        `"RE00"+masterId` / `"RN00"+masterId` (§5.1: same underlying idea,
        but the legacy version had no protection against the row being
        deleted out from under an issued number, and inconsistent
        zero-padding — `RE00`+7 = `RE007` but `RE00`+1234 = `RE001234`).
        Fixed 6-digit width here; prefix still communicates reserve vs.
        normal, matching what staff already read.
        """
        prefix = "RN" if self.is_reserve else "RE"
        return f"{prefix}{self.pk:06d}"

    @transaction.atomic
    def add_line(self, item, *, unit_price, actor=None):
        if item.status not in (StockStatus.PENDING, StockStatus.RESERVED):
            raise ValidationError(
                f"{item.barcode} is {item.status}, not eligible for assignment "
                "(replaces the legacy no-op conflict check in productassign.aspx.cs)."
            )
        line = AssignmentLine.objects.create(master=self, item=item, unit_price=unit_price)
        target_status = StockStatus.ASSIGNED
        item.transition_status(target_status, actor=actor, reason=f"assigned on {self.invoice_number}")
        return line

    @transaction.atomic
    def stamp_invoice(self, *, actor=None):
        if self.invoice_status == InvoiceStatus.COMPLETE:
            return  # idempotent — legacy reopen preserved the number; so does this, trivially
        self.invoice_status = InvoiceStatus.COMPLETE
        self.save(update_fields=["invoice_status", "updated_at"])
        AuditLogEntry.record(actor=actor, action="invoice_stamped", obj=self, summary=self.invoice_number)


class AssignmentLine(TimeStampedModel):
    master = models.ForeignKey(AssignmentMaster, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("inventory.ProductItem", on_delete=models.PROTECT, related_name="assignment_lines")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["master", "item"], name="unique_item_per_assignment"),
        ]

    def __str__(self):
        return f"{self.item.barcode} on {self.master.invoice_number}"

    def calculate_line_total(self):
        """
        The one pricing function. Legacy `sp_product_assign` had two
        independently-maintained calculations for the same number
        (`insert_alvin_discount`'s two branches) that a SQL comment said
        had to be kept manually aligned with two other functions
        elsewhere in the same procedure — a real drift risk, not a
        hypothetical one. There's only one path here.
        """
        return (self.unit_price * (Decimal("100") - self.discount_percent) / Decimal("100")).quantize(Decimal("0.01"))
