"""
Zebra label printing — customizable tag designer + ZPL generation.

Replaces the ZPL generation half of `PrintBarcode.aspx.cs` (the handheld
scanner ingest half is still not built — see the app-level TODO in
django-rebuild-plan.md §3). Legacy hardcoded five fixed layouts
(jewellery/stone/finding/metal/default) directly in C# string templates —
the only way to change what a label looked like was to edit code and
redeploy. Here a `LabelTemplate` + ordered `LabelField` set is a real,
editable row set: staff can add/remove/reposition fields, change fonts,
toggle visibility, and save, with no code change or redeploy.

Findings this addresses:
  - No customization existed at all in the legacy version.
  - The legacy jewellery template silently defaulted missing colour to
    "Pink" and missing size to "US 7" — a placeholder that could mislabel
    a real ring with no visual indication anything was defaulted. Here a
    blank value renders blank; there is no invented fallback.
  - Preserve the ZPL printer-setup preamble and the RFID write command
    (`^RS8`, `^RFW,a,2,,A` with the barcode as payload) exactly — those
    are printer/media-specific behavior already proven against real
    hardware, not legacy cruft to redesign. See `zpl.py` for where that
    line is drawn between "kept verbatim" and "new code."
"""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class LabelTemplate(TimeStampedModel):
    class Category(models.TextChoices):
        JEWELLERY = "JW", "Jewellery"
        STONE = "ST", "Stone"
        FINDING = "FI", "Finding"
        METAL = "MT", "Metal"
        ANY = "ANY", "Any category (fallback)"

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=5, choices=Category.choices, default=Category.ANY)
    is_default = models.BooleanField(
        default=False,
        help_text="Used automatically when printing an item in this category without picking a template explicitly. Only one default per category.",
    )
    width_dots = models.PositiveIntegerField(default=785, help_text="Label width in printer dots — matches the ZPL ^PW command.")
    height_dots = models.PositiveIntegerField(default=400, help_text="Label height in printer dots. Design-canvas only; ZPL itself doesn't need a ^LL for continuous/RFID stock.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="label_templates"
    )

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class LabelField(TimeStampedModel):
    class FieldKey(models.TextChoices):
        BARCODE_NUMBER = "barcode_number", "Barcode number (text)"
        BARCODE_IMAGE = "barcode_image", "Barcode (scannable)"
        REFERENCE_ID = "reference_id", "Reference / SKU"
        PRODUCT_NAME = "product_name", "Product name"
        METAL = "metal", "Metal"
        METAL_PURITY = "metal_purity", "Metal purity"
        STONE = "stone", "Stone"
        COLOUR = "colour", "Colour"
        QUALITY = "quality", "Quality"
        WEIGHT = "weight", "Net weight"
        PRICE = "price", "Price"
        CURRENCY = "currency", "Currency"
        SIZE = "size", "Size"
        COMPANY_NAME = "company_name", "Company name"
        STATIC_TEXT = "static_text", "Custom text"

    class Align(models.TextChoices):
        LEFT = "L", "Left"
        CENTER = "C", "Center"
        RIGHT = "R", "Right"

    template = models.ForeignKey(LabelTemplate, on_delete=models.CASCADE, related_name="fields")
    field_key = models.CharField(max_length=20, choices=FieldKey.choices)
    static_text = models.CharField(
        max_length=200, blank=True,
        help_text="Full text when field_key = Custom text; otherwise an optional label/prefix in front of the field's value.",
    )
    x = models.PositiveIntegerField(default=10)
    y = models.PositiveIntegerField(default=10)
    font_size = models.PositiveIntegerField(default=24)
    bold = models.BooleanField(default=False)
    align = models.CharField(max_length=1, choices=Align.choices, default=Align.LEFT)
    box_width = models.PositiveIntegerField(default=300, help_text="Text box width in dots — drives ZPL ^FB wrapping/alignment.")
    visible = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.get_field_key_display()} @ ({self.x},{self.y}) on {self.template}"
