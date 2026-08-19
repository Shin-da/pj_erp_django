"""
Location-to-location transfers.

Status: minimal header model only, enough for `tracker` to link a scan
session to the transfer it produced. Full build-out (line items, the
from/destination routing rules documented in
SCAN-TRANSFER-WORKFLOW.md §3, and fixing the legacy return-transfer gap —
`btnreturn_Click` in `ProductTransferList.aspx.cs` was entirely commented
out behind a live button, INVENTORY-AND-INVOICING.md §4.5 — return_status
must actually be settable here) is not yet done. See
REBUILD-ARCHITECTURE-AND-BUDGET.md §2 / §5 for sequencing: `inventory` and
`tracker` come first.
"""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class TransferStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    COMPLETE = "COMPLETE", "Complete"
    RETURNED = "RETURNED", "Returned"


class Transfer(TimeStampedModel):
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

    def __str__(self):
        return f"Transfer #{self.pk}: {self.from_location.code} -> {self.to_location.code}"
