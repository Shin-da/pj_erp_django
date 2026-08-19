"""
NOT YET BUILT.

Will replace `device_dataform.aspx` (handheld scanner ingest) and the ZPL
generation in `PrintBarcode.aspx.cs`.

Findings this will need to address:
  - One hardcoded shared secret authenticated every handheld device
    (`device_dataform.aspx.cs`, confirmed in two places in source). Use
    per-device tokens (a `ScannerDevice` model with a real credential per
    unit) instead.
  - Validation failures (bad secret, bad location) were still logged into
    `tbldevice_data` marked "pending" rather than rejected — a log-flood
    surface. Reject bad auth outright.
  - `manage_stock`'s toggle read live table state instead of a pre-batch
    snapshot, making some scans no-ops and silently un-assigning items a
    different workflow had legitimately assigned (confirmed by controlled
    test, INVENTORY-AND-INVOICING.md §9a.2, later fixed in the legacy
    `active-sync` branch via a snapshot-first rewrite — port that fixed
    design natively via `inventory.ProductItem.transition_status`, not
    the patched-toggle version).
  - Preserve the ZPL template set (JW/ST/FI/MT/default) and the RFID
    write command (`^RFW,a,2,,A` with the barcode as payload) exactly —
    those are proven hardware behavior, not legacy cruft.
"""

from django.db import models  # noqa: F401
