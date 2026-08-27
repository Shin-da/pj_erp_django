"""
Payments — reseller side and supplier side.

Replaces `assign_paymentpage.aspx` + `payment_page.aspx` (two
near-identical pages, differing only by lookup axis — product vs.
assignment master, per INVENTORY-AND-INVOICING.md §6) and the supplier-
side cluster (`supplierbase_product_paymnet.aspx`,
`Consignment_payment.aspx`, `supplier_base_paymnetdeatils.aspx`) +
`tblassignpayment_transaction` / `tblpayment_transaction`.

One payments app with two clearly-named models instead of two duplicated
page trees that happened to share almost all of their logic — the legacy
duplication wasn't a deliberate design, just two pages built separately
for what was really one concept viewed from two directions.

Also replaces `invoicecancel_approval.aspx` + `sp_invoicecancel_mgmt`.
Legacy finding this fixes: approving a cancellation triggered a *second*
physical inventory return per barcode on top of whatever
`ProductReturn.aspx` had already done for the same items, then fired a
full Tiara sync unconditionally (confirmed reading
`invoicecancel_approval.aspx.cs`). `InvoiceCancellation.approve()` here
calls `ProductItem.transition_status()` exactly once per item.
"""

from django.conf import settings
from django.db import models, transaction

from apps.core.models import TimeStampedModel, AuditLogEntry
from apps.assignment.models import InvoiceStatus
from apps.inventory.models import StockStatus


class ResellerPayment(TimeStampedModel):
    """Payment received from a reseller against an assignment/invoice."""

    assignment = models.ForeignKey(
        "assignment.AssignmentMaster", on_delete=models.PROTECT, related_name="payments"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_on = models.DateField()
    reference_note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="reseller_payments_recorded"
    )

    class Meta:
        ordering = ["-paid_on"]

    def __str__(self):
        return f"{self.assignment.invoice_number}: {self.amount}"


class SupplierPayment(TimeStampedModel):
    """Payment made to a supplier — replaces the supplier-side payment cluster."""

    supplier = models.ForeignKey("catalogue.Supplier", on_delete=models.PROTECT, related_name="payments")
    product = models.ForeignKey(
        "catalogue.ProductMaster", null=True, blank=True, on_delete=models.SET_NULL, related_name="supplier_payments"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_on = models.DateField()
    reference_note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="supplier_payments_recorded"
    )

    class Meta:
        ordering = ["-paid_on"]

    def __str__(self):
        return f"{self.supplier}: {self.amount}"


class InvoiceCancellation(TimeStampedModel):
    assignment = models.ForeignKey(
        "assignment.AssignmentMaster", on_delete=models.PROTECT, related_name="cancellations"
    )
    reason = models.CharField(max_length=255, blank=True)
    approved = models.BooleanField(null=True, blank=True, help_text="Null = pending approval.")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="cancellations_requested"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="cancellations_approved"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Cancel {self.assignment.invoice_number} ({'pending' if self.approved is None else self.approved})"

    @transaction.atomic
    def approve(self, *, actor=None):
        """
        Exactly one inventory return per item — the legacy version ran
        this in addition to whatever ProductReturn.aspx had already done
        for the same barcodes, a real double-return bug.

        Both SOLD and ASSIGNED lines come back. Only SOLD was handled
        before, which meant cancelling an invoice whose pieces were still
        out with the reseller marked the invoice CANCELLED while leaving
        every piece ASSIGNED — stock permanently out against a document
        that no longer exists. RESERVED is included for the same reason.
        Anything already PENDING is skipped rather than transitioned,
        since `transition_status` rejects PENDING -> PENDING and a
        partially-returned invoice must still be cancellable.
        """
        returnable = {StockStatus.SOLD, StockStatus.ASSIGNED, StockStatus.RESERVED}
        for line in self.assignment.lines.select_related("item").all():
            if line.item.status in returnable:
                line.item.transition_status(StockStatus.PENDING, actor=actor, reason=f"invoice {self.assignment.invoice_number} cancelled")
        self.assignment.invoice_status = InvoiceStatus.CANCELLED
        self.assignment.save(update_fields=["invoice_status", "updated_at"])
        self.approved = True
        self.approved_by = actor
        self.save(update_fields=["approved", "approved_by", "updated_at"])
        AuditLogEntry.record(actor=actor, action="invoice_cancel_approved", obj=self.assignment, summary=self.assignment.invoice_number)

    def reject(self, *, actor=None):
        self.approved = False
        self.approved_by = actor
        self.save(update_fields=["approved", "approved_by", "updated_at"])
