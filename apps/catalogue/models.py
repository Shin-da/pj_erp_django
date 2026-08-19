"""
Product catalogue — the design/SKU level.

Replaces `tblproduct_master` + its lookup tables (`tbljewellery_type`,
metal/purity/currency masters).

Legacy findings this fixes:
  - Every price/quantity/date column on `tblproduct_master` was typed
    `nvarchar` (`_schema_columns.txt` confirms this schema-wide — only a
    handful of newer columns like `metalrate` were proper `decimal`).
    Real `DecimalField`/`DateField` types here, so arithmetic and sorting
    are correct by construction instead of by string-comparison luck.
  - `tblproduct_master.company_locationid` put location on the *design*
    record, so every physical item sharing a design shared one location —
    the root cause of the transfer bug documented in
    INVENTORY-AND-INVOICING.md §9a.1/§9b.3 (moving one barcode silently
    "moved" every sibling barcode's master-level location). Location is
    deliberately NOT a field on `ProductMaster` here — it lives on
    `inventory.ProductItem`, the physical-item level, where the legacy
    schema already had the columns for this (`transfer_status`,
    `transfer_id`) but no procedure ever wrote them.
"""

from django.db import models

from apps.core.models import TimeStampedModel


class Category(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True, help_text="e.g. JW, ST, FI, MT — drives ZPL label template routing.")

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Currency(TimeStampedModel):
    code = models.CharField(max_length=10, unique=True)
    symbol = models.CharField(max_length=5, blank=True)

    class Meta:
        verbose_name_plural = "currencies"

    def __str__(self):
        return self.code


class Metal(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Purity(TimeStampedModel):
    metal = models.ForeignKey(Metal, on_delete=models.PROTECT, related_name="purities")
    name = models.CharField(max_length=50)

    class Meta:
        verbose_name_plural = "purities"
        unique_together = [("metal", "name")]

    def __str__(self):
        return f"{self.metal} {self.name}"


class Supplier(TimeStampedModel):
    name = models.CharField(max_length=150)
    reference_code = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return self.name


class ProductMaster(TimeStampedModel):
    reference_id = models.CharField(max_length=100, blank=True, db_index=True)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="products")
    metal = models.ForeignKey(Metal, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    purity = models.ForeignKey(Purity, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")

    net_weight = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    gross_weight = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.reference_id})" if self.reference_id else self.name
