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
    fixed-width zero-padded number derived from the row's own
    primary key (`_generated_invoice_number`, stamped once at save time)
    fixes the padding inconsistency. NOTE: there is no separate
    `invoice_seq` column and no `models.Sequence` default -- an earlier
    version of this docstring described one. Numbers are still pk-derived,
    exactly as in the legacy system; what changed is the fixed width and
    the soft-delete that stops a row disappearing out from under an issued
    number. If a genuinely gapless reserved sequence is ever required,
    that is still to be built.
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


class ResellerGroup(TimeStampedModel):
    """
    A grouping of resellers/clients — the "reseller group" the business
    actually organises people by day to day (regional groups, the set of
    resellers one coordinator handles, etc.).

    New concept, no legacy table behind it: `tblresellermaster` was flat.
    Grouping was maintained outside the system, which is why "who's in
    which group" was never answerable from a screen.

    Kept deliberately thin — a group is a label plus its members. It does
    NOT own stock, does NOT get invoiced, and nothing about assignment or
    pricing routes through it. If groups later need their own commercial
    terms, that's a real decision to make then, not a field to add
    speculatively now.
    """

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, unique=True, help_text="Short code used on screens and reports, e.g. GRP-A.")
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class ResellerLocation(TimeStampedModel):
    """
    Replaces `tblresellerlocationMaster` — the reseller-side "branch" an
    invoice is issued under (L'ESPÉRANCE, ONELIVE, RDR, LuxeTrust…).

    Still NOT `locations.Location`: that is a *company* site where stock
    physically sits. This is whose banner and logo appear at the top of
    the printed invoice. The legacy schema kept the two apart and so does
    this (INVENTORY-AND-INVOICING.md §2).

    `logo` is the file `tblresellerlocationMaster.invoicelogo` pointed at,
    migrated across from `Documents/GroupImages/`. Without it a rendered
    invoice is unbranded, which is the single most visible difference
    between a real invoice and a printout.
    """

    name = models.CharField(max_length=150)
    remarks = models.CharField(max_length=200, blank=True)
    # FileField, not ImageField: ImageField needs Pillow purely to
    # validate dimensions, and nothing here cares about dimensions.
    logo = models.FileField(upload_to="reseller_logos/", blank=True)
    legacy_id = models.IntegerField(
        null=True, blank=True, unique=True, db_index=True,
        help_text="tblresellerlocationMaster.nid — how imported invoices find their banner.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Reseller(TimeStampedModel):
    """Replaces `tblresellermaster`. Deliberately NOT the same concept as
    `locations.Location` — see INVENTORY-AND-INVOICING.md §2: "Company
    locations and reseller locations are different concepts. Don't
    conflate them" (a distinction the legacy schema itself maintained
    correctly, worth keeping)."""

    name = models.CharField(max_length=150)
    reference_code = models.CharField(max_length=50, blank=True)

    # Printed on the invoice, under Name / Address / Email-Phone. All three
    # exist on tblResellerMaster and were simply not carried across on the
    # first import pass.
    address = models.CharField(max_length=255, blank=True)
    contact = models.CharField(max_length=100, blank=True)
    email = models.CharField(max_length=150, blank=True)

    # The legacy invoice prints this as "Res No." — it is nothing more
    # than tblResellerMaster.nid shown to the customer as a reference.
    # Kept so a reissued invoice matches the one they already hold.
    legacy_id = models.IntegerField(
        null=True, blank=True, unique=True, db_index=True,
        help_text='tblResellerMaster.nid. Printed on invoices as "Res No.".',
    )
    group = models.ForeignKey(
        ResellerGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="clients",
        help_text="Nullable on purpose — every existing reseller row stays valid and simply shows as ungrouped until someone files it.",
    )
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


class CommissionType(models.TextChoices):
    """
    Ported from pj-accounting's computeCommission() (src/invoices.js) —
    same two rules, same vocabulary, so a commission concept means the
    same thing wherever it's used across the two systems:
      GOLD    -> commission_rate is pesos per gram of the product's
                 net_weight
      JEWELRY -> commission_rate is a fraction (e.g. 0.05) of this
                 line's own total
    """

    GOLD = "GOLD", "Gold (rate per gram)"
    JEWELRY = "JEWELRY", "Jewelry (rate x line total)"


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
    reseller_location = models.ForeignKey(
        ResellerLocation, null=True, blank=True, on_delete=models.SET_NULL, related_name="assignments",
        help_text="Which reseller branch this was issued under — drives the invoice banner and logo. Legacy tblProductAssignMaster.reseller_locationid.",
    )
    is_reserve = models.BooleanField(
        default=False, help_text="Reserve-path assignment (legacy RN00 prefix) vs. normal reseller assignment (RE00)."
    )
    invoice_number = models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        help_text="Stored so imported legacy numbers (RE00128, RN00004, …) survive. New rows get a fixed-width RE/RN + id if left blank.",
    )
    invoice_status = models.CharField(max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="assignments_created"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.invoice_number or f"{'RN' if self.is_reserve else 'RE'}(unsaved)"

    def _generated_invoice_number(self):
        prefix = "RN" if self.is_reserve else "RE"
        return f"{prefix}{self.pk:06d}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.invoice_number and self.pk:
            generated = self._generated_invoice_number()
            type(self).all_objects.filter(pk=self.pk).update(invoice_number=generated)
            self.invoice_number = generated

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
    """
    Commission fields (added after the 27 Aug 2026 request to bring
    pj-accounting's invoice/commission idea into this app): deliberately
    NOT a separate invoice document, same as the rest of this file — a
    commission is just two more numbers on the line that already carries
    the price. Foundation only for now; pj-accounting's manual-entry
    form, per-partner reporting, and audit-log listing are explicitly
    deferred until the rest of this app's UI (Phase 8) exists to host
    them — see django-rebuild-plan.md.
    """

    master = models.ForeignKey(AssignmentMaster, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("inventory.ProductItem", on_delete=models.PROTECT, related_name="assignment_lines")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    commission_type = models.CharField(
        max_length=20,
        choices=CommissionType.choices,
        blank=True,
        help_text="Leave blank if this line carries no reseller commission.",
    )
    commission_rate = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Pesos per gram for GOLD, or a fraction (e.g. 0.05) of the line total for JEWELRY.",
    )
    commission_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Auto-computed from commission_rate/commission_type on save unless commission_overridden is set.",
    )
    commission_overridden = models.BooleanField(
        default=False,
        help_text="True once a human has set commission_value directly — mirrors pj-accounting's commissionValue-supplied-by-admin override rule. Auto-calculation stops touching it after that; use set_commission_override() to flip it deliberately rather than editing the field directly.",
    )

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

    def calculate_commission(self):
        """
        Ported from pj-accounting's computeCommission() (src/invoices.js).
        Returns None when there's nothing to compute (no rate, no type,
        a zero rate, or — for GOLD — a product with no net_weight
        recorded) so the caller decides what to do with "nothing to
        compute" rather than this silently becoming 0. See save().
        """
        if not self.commission_rate or not self.commission_type:
            return None
        if self.commission_type == CommissionType.GOLD:
            weight = self.item.product.net_weight
            if weight is None:
                return None
            return (self.commission_rate * weight).quantize(Decimal("0.01"))
        if self.commission_type == CommissionType.JEWELRY:
            return (self.commission_rate * self.calculate_line_total()).quantize(Decimal("0.01"))
        return None

    def save(self, *args, **kwargs):
        if not self.commission_overridden:
            auto = self.calculate_commission()
            self.commission_value = auto if auto is not None else Decimal("0")
        super().save(*args, **kwargs)

    def set_commission_override(self, value, *, actor=None):
        """
        The one deliberate path that can move commission_value away from
        calculate_commission()'s answer — mirrors pj-accounting's
        admin-supplied commissionValue override. Logged, unlike the
        ordinary auto-recalculation that happens on every save().
        """
        self.commission_overridden = True
        self.commission_value = Decimal(value).quantize(Decimal("0.01"))
        self.save(update_fields=["commission_value", "commission_overridden", "updated_at"])
        AuditLogEntry.record(
            actor=actor,
            action="commission_overridden",
            obj=self,
            summary=f"{self.item.barcode} on {self.master.invoice_number}: commission set to {self.commission_value}",
        )
