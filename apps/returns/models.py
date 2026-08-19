"""
NOT YET BUILT.

Will replace `ProductReturn.aspx`. Legacy finding to address deliberately
here: a "reserved" or "reassigned" barcode never actually became free
inventory in the old app — `return_product_by_barcode` ran first, but
`reassign()`/`reserve()` immediately re-claimed the item in the same
postback, so only a plain return with no follow-up status left stock
genuinely open (confirmed reading `ProductReturn.aspx.cs::btnSave_Click`).
Model this explicitly as a state machine on `inventory.ProductItem`
(see `apps.inventory.models.VALID_TRANSITIONS`) rather than three
sequential, easy-to-misorder procedure calls.
"""

from django.db import models  # noqa: F401
