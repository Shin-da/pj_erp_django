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

import re
from decimal import Decimal, InvalidOperation

from django.conf import settings
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


_DFLT_PREFIX_RE = re.compile(r"^\s*DFLT\s*[-–—:|/]\s*", re.IGNORECASE)


def strip_dflt_prefix(value):
    """Drop a legacy 'DFLT - ' purity prefix. Keep the rest (18K, PT900, …)."""
    text = (value or "").strip()
    if not text:
        return ""
    cleaned = _DFLT_PREFIX_RE.sub("", text).strip()
    return cleaned or text


def format_metal_purity_label(purity_name, country_name="", country_code=""):
    """Stock-report karat line: 18K-Japan Gold. Drop a DEFAULT/DFLT suffix."""
    purity = strip_dflt_prefix(purity_name)
    if not purity or purity == "-":
        return ""
    code = (country_code or "").strip().upper()
    country = (country_name or "").strip()
    if not country or code in {"DFLT", "DEFAULT"} or country.upper() in {"DEFAULT", "DFLT"}:
        return purity
    suffix = f"-{country}"
    if purity.endswith(suffix):
        return purity
    return f"{purity}-{country}"


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


class PurchaseType(models.TextChoices):
    """tblproduct_master.product_type — purchase vs supplier consignment."""

    PURCHASED = "purchased", "Purchased"
    CONSIGNMENT = "consignment", "Consignment"


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

    product_type = models.CharField(
        max_length=20,
        choices=PurchaseType.choices,
        default=PurchaseType.PURCHASED,
        db_index=True,
        help_text="tblproduct_master.product_type. Consignment lots keep a due_date for return/settle reminders.",
    )
    purchase_date = models.DateField(
        null=True,
        blank=True,
        help_text="tblproduct_master.purchase_date — when the lot was taken in.",
    )
    due_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="tblproduct_master.due_date — consignment return/settle-by date. Warn only; stock is not returned automatically.",
    )

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
    is_verified = models.BooleanField(
        default=True,
        help_text="False for a design created from an unverified source (e.g. photographed "
        "into almarphoto) with no matching iadmin/RFID record yet — legacy_id is null and "
        "nothing here has been confirmed against actual tagged stock. A later legacy sync "
        "that finds a matching barcode/reference_id should flip this back to True and reuse "
        "this row rather than creating a duplicate.",
    )

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["product_type", "due_date"], name="catalogue_pm_consign_due"),
        ]
        permissions = [
            (
                "can_intake_stock",
                "Can bring in stock via Excel upload or one-piece intake (C2 fix — "
                "SYSTEM-AUDIT-2026-09-11.md)",
            ),
            (
                "can_upload_photos",
                "Can upload design photos by PJ / barcode (separate from stock intake)",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.reference_id})" if self.reference_id else self.name

    def days_until_due(self, today=None):
        """None when there is no due_date. Negative means overdue."""
        if not self.due_date:
            return None
        if today is None:
            from django.utils import timezone
            today = timezone.localdate()
        return (self.due_date - today).days

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

    @property
    def display_purity(self):
        if not self.purity_id:
            return ""
        label = strip_dflt_prefix(self.purity.name)
        return "" if label in {"", "-"} else label

    @property
    def display_metal(self):
        purity = self.display_purity
        # Stock report already stores the origin suffix on the purity label.
        if purity and "-" in purity:
            return purity
        parts = []
        if self.metal_id and (self.metal.name or "").strip() not in {"", "Unspecified"}:
            parts.append(self.metal.name.strip())
        if purity:
            parts.append(purity)
        return " ".join(parts)

    @property
    def display_net_weight(self):
        """Master net_wt, else the jewellery metal-detail weight stored as gold_weight."""
        if self.net_weight is not None:
            return self.net_weight
        raw = (self.gold_weight or "").strip().replace(",", "")
        if not raw:
            return None
        try:
            return Decimal(raw)
        except (InvalidOperation, ValueError):
            return None


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


class ProductIntakeBatch(TimeStampedModel):
    """One jewellery Excel (or one-piece form) drop — tblUploadexcel_list."""

    class Source(models.TextChoices):
        EXCEL = "excel", "Jewellery Excel"
        FORM = "form", "One piece"

    class Status(models.TextChoices):
        SUCCESS = "success", "Caught"
        PARTIAL = "partial", "Caught with row errors"
        FAILED = "failed", "Not this file"

    serial_no = models.PositiveIntegerField(db_index=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.EXCEL)
    filename = models.CharField(max_length=255, blank=True)
    workbook = models.FileField(upload_to="intake_uploads/%Y/%m/", blank=True)
    sheet = models.CharField(max_length=100, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="product_intake_batches",
    )
    location = models.ForeignKey(
        "locations.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="product_intake_batches",
    )
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUCCESS)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Excel {self.serial_no} ({self.filename or self.source})"

    @property
    def row_count(self):
        return self.created_count + self.updated_count


class ProductIntakeLine(TimeStampedModel):
    """One PJ from an intake batch — the Excel Logs popup of barcodes."""

    class Action(models.TextChoices):
        CREATED = "created", "New"
        UPDATED = "updated", "Updated"
        ERROR = "error", "Skipped"

    batch = models.ForeignKey(
        ProductIntakeBatch, on_delete=models.CASCADE, related_name="lines",
    )
    barcode = models.CharField(max_length=100, blank=True, db_index=True)
    reference = models.CharField(max_length=100, blank=True)
    action = models.CharField(max_length=10, choices=Action.choices)
    row_number = models.PositiveIntegerField(default=0)
    message = models.CharField(max_length=500, blank=True)
    item = models.ForeignKey(
        "inventory.ProductItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="intake_lines",
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.barcode or 'row'} — {self.action}"
