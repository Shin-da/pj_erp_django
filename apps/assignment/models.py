"""
NOT YET BUILT.

Will replace `productassign.aspx` + `tblProductAssignMaster` /
`tblproductassign` + invoice number stamping (`ResellerPaymentInvoice.aspx`).

Findings this will need to address when built (see
perfect-jewel-system-landscape.md §1.1 and §6 of INVENTORY-AND-INVOICING.md):
  - Invoice numbers were derived from the row primary key (`"RE00"+masterId`)
    with no sequence table — gaps, no padding discipline. Use a real
    sequence/AutoField-derived number here.
  - `sp_product_assign` (`insert_master`) also wrote a room-allotment
    record (`tblRoomAllotmentMaster`) on every assignment — confirm with
    the business whether that's a real showroom/consignment-slot concept
    worth carrying forward before deciding whether this app needs a
    `rooms`/`display_slot` concept at all.
  - `productassign.aspx.cs`'s room-availability check didn't exclude
    already-allocated rooms (unlike `Rfid_scan.aspx.cs`, which did) —
    don't reintroduce that inconsistency; there should be exactly one
    availability check, not two that disagree.
  - Two independently-maintained pricing calculations existed in the SP
    (`insert_alvin_discount`, per-comment "must stay aligned with
    get_reseller_invoicedata_edit / get_reseller_invoicedata") — pricing
    here should be one function, not two kept in sync by convention.
  - Reopening an invoice in the legacy app regenerated and silently
    overwrote the stored PDF every page load, even though the invoice
    number stayed fixed — decide deliberately whether re-render-on-view
    is even the right model here.
"""

from django.db import models  # noqa: F401
