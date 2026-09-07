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

from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


class Category(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(
        max_length=32,
        unique=True,
        help_text="JW / ST / FI / MT — drives ZPL label template routing (legacy tbljewellery_type).",
    )

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
    legacy_id = models.IntegerField(
        null=True, blank=True, unique=True, db_index=True,
        help_text="tblproduct_master.nid — lets a re-sync from iadmin update this exact design instead of duplicating it.",
    )
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    subcategory = models.CharField(
        max_length=100,
        blank=True,
        help_text="Legacy tblsub_category_master name (Ring, Necklace, …). Category itself is the jewellery type (JW/ST/FI/MT) used for ZPL routing.",
    )
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="products")
    metal = models.ForeignKey(Metal, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    purity = models.ForeignKey(Purity, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")

    net_weight = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    gross_weight = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Tag / jewellery attribute columns from tblproduct_master + detail tables.
    # `gold_weight` / `diamond_weight` are the numbers printed as G-… / D-… on tags.
    colour = models.CharField(max_length=50, blank=True)
    size = models.CharField(max_length=50, blank=True)
    quality = models.CharField(max_length=50, blank=True)
    stone = models.CharField(
        max_length=100,
        blank=True,
        help_text="Legacy tblproduct_master.stone (often empty).",
    )
    gold_weight = models.CharField(
        max_length=40,
        blank=True,
        help_text="Metal weight from tbljewellery_metal_details — printed as G-{value}.",
    )
    diamond_weight = models.CharField(
        max_length=40,
        blank=True,
        help_text="Diamond carat/weight from tbljewellery_stone_details — printed as D-{value}.",
    )

    # ---- Rates the legacy invoice multiplies prices by ----------------
    #
    # Every amount on `ResellerPaymentInvoice.aspx` is
    # `selling_price * convert_rate`, where the rate comes from the
    # product master: `update_convert_rate` when `ratechange_status` is
    # 'apply', otherwise `Converte_rate` (see
    # scripts/018_product_master_management_invoice.sql in the legacy
    # repo). Leaving these out of the first import pass meant any invoice
    # this system rendered could disagree with the PDF the customer
    # already holds, for the same invoice. They are carried for that
    # reason — nothing else uses them yet.
    #
    # `metal_rate` is the per-gram price shown in the invoice's "Price
    # Per Gram" column, which the legacy page reveals only for gold.
    metal_rate = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="tblproduct_master.metalrate — per-gram price, shown on gold invoice lines.",
    )
    convert_rate = models.DecimalField(
        max_digits=12, decimal_places=6, default=Decimal("1"),
        help_text="tblproduct_master.Converte_rate. Multiplies price on the printed invoice.",
    )
    update_convert_rate = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True,
        help_text="Pending replacement rate; used instead of convert_rate when rate_change_status is 'apply'.",
    )
    rate_change_status = models.CharField(
        max_length=20, blank=True,
        help_text="'apply' means use update_convert_rate; anything else means use convert_rate.",
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.reference_id})" if self.reference_id else self.name

    @property
    def effective_rate(self):
        """
        The one place that decides which conversion rate applies. The
        legacy system re-implemented this CASE across several
        stored-procedure branches that a SQL comment warned had to be
        kept aligned by hand — there is one copy here.
        """
        if self.rate_change_status == "apply" and self.update_convert_rate is not None:
            return self.update_convert_rate
        return self.convert_rate if self.convert_rate is not None else Decimal("1")


class ProductImage(TimeStampedModel):
    """
    Photographs of a product design. Replaces the legacy
    `tblproduct_master.product_image` / `.certificate_image` string columns
    (files served from `iadmin/image/Product_Images/`) and the never-
    populated per-item `tblproduct_detail_master.item_image`.

    Attached at the design (ProductMaster) level, not the physical item:
    the legacy schema kept the main photo there and items sharing a design
    share its photography. A genuinely one-off shot still hangs off its
    design — there is a ProductMaster per design already.

    FileField, not ImageField, to match `assignment.ResellerLocation.logo`:
    dimension validation would make Pillow a hard *runtime* dependency for
    no gain. `import_product_images` resizes on the way in; nothing served
    needs width/height.
    """

    class Kind(models.TextChoices):
        PHOTO = "PHOTO", "Product photo"
        CERTIFICATE = "CERT", "Certificate"
        OTHER = "OTHER", "Other"

    product = models.ForeignKey(
        ProductMaster, on_delete=models.CASCADE, related_name="images"
    )
    image = models.FileField(upload_to="product_images/%Y/%m/")
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.PHOTO)
    is_primary = models.BooleanField(
        default=False,
        help_text="Shown first wherever a single thumbnail is needed.",
    )
    caption = models.CharField(max_length=200, blank=True)
    source_filename = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Original file this came from — a re-import skips a (product, source_filename) pair already stored.",
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-is_primary", "order", "id"]
        indexes = [models.Index(fields=["product", "is_primary"])]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_primary=True),
                name="one_primary_image_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.product} — {self.get_kind_display()}"
