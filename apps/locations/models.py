"""
Locations.

Replaces `tblcompany_locations`.

Two confirmed legacy findings this fixes:
  1. `location_code = 'HO'` was a hardcoded literal string compared
     throughout the codebase (InventoryLocationHelper.BindToLocationDropdown,
     transfer routing, etc.) — renaming that location in the UI would have
     silently broken transfer routing (INVENTORY-AND-INVOICING.md §2).
     `location_type` here is a real enum field instead.
  2. `bstatus` and `active_status` were two independent flags with
     inconsistently-applied meaning — some dropdowns filtered on `bstatus`
     alone, others on both, and the difference silently let an inactive
     location still be picked as a transfer *source* but not a
     *destination* (undocumented, discovered by reading the code). One
     `is_active` flag here, via `core.SoftDeleteModel`.
"""

from django.db import models

from apps.core.models import SoftDeleteModel


class LocationType(models.TextChoices):
    HEAD_OFFICE = "HEAD_OFFICE", "Head Office"
    BRANCH = "BRANCH", "Branch"
    SHOWROOM = "SHOWROOM", "Showroom"
    WAREHOUSE = "WAREHOUSE", "Warehouse"
    PULLOUT = "PULLOUT", "Pullout"
    OTHER = "OTHER", "Other"


class Location(SoftDeleteModel):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, unique=True, db_index=True)
    location_type = models.CharField(
        max_length=20, choices=LocationType.choices, default=LocationType.BRANCH
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def is_head_office(self):
        return self.location_type == LocationType.HEAD_OFFICE
