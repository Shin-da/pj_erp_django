"""
NOT YET BUILT.

Will replace `assign_paymentpage.aspx` / `payment_page.aspx` (two
near-identical pages differing only by lookup axis — product vs. assignment
master, per INVENTORY-AND-INVOICING.md §6) and the supplier-side payment
cluster (`supplierbase_product_paymnet.aspx`, `Consignment_payment.aspx`).
One payments app, not two duplicated page trees, is the point.
"""

from django.db import models  # noqa: F401
