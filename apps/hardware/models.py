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

from .media import DEFAULT_MEDIA_PROFILE, DEFAULT_PRINTER_DPI, get_media_profile, scale_dot


class LabelTemplate(TimeStampedModel):
    class Category(models.TextChoices):
        # Codes match catalogue.Category rows from the legacy import
        # (JWL/SN/FN/…), not the shortened JW/ST/FI aliases in older docs.
        JEWELLERY = "JWL", "Jewellery"
        STONE = "SN", "Stone"
        FINDING = "FN", "Finding"
        METAL = "MT", "Metal"
        GOLD_BRICKS = "GB", "Gold Bricks"
        SEMI_PRECIOUS = "SPP", "Semi Precious"
        UNCATEGORISED = "UNK", "Uncategorised"
        ANY = "ANY", "Any category (fallback)"

    class MediaProfile(models.TextChoices):
        IRYS_STANDARD = "irys_standard", "Irys Standard RFID (25×13 + 50mm tail)"
        BLANK = "blank", "Blank rectangle"

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=5, choices=Category.choices, default=Category.ANY)
    is_default = models.BooleanField(
        default=False,
        help_text="Used automatically when printing an item in this category without picking a template explicitly. Only one default per category.",
    )
    media_profile = models.CharField(
        max_length=40,
        choices=MediaProfile.choices,
        default=DEFAULT_MEDIA_PROFILE,
        help_text="Paper die-cut overlay in the designer (Irys jewellery RFID vs free rectangle).",
    )
    dpi = models.PositiveIntegerField(
        default=DEFAULT_PRINTER_DPI,
        help_text="Must match the Zebra printer DPI (jewellery RFID units are usually 300). Wrong DPI compresses both faces into one panel.",
    )
    width_dots = models.PositiveIntegerField(
        default=886,
        help_text="Label width in printer dots — matches the ZPL ^PW command. Irys Standard @ 300 DPI ≈ 886 (75 mm).",
    )
    height_dots = models.PositiveIntegerField(
        default=308,
        help_text="Label height in printer dots (designer canvas). Continuous RFID stock does not emit ^LL. Irys @ 300 DPI ≈ 308 (26 mm).",
    )
    offset_x = models.IntegerField(
        default=0,
        help_text="Print X nudge in dots (positive shifts right). Use to align with the physical die-cut.",
    )
    offset_y = models.IntegerField(
        default=0,
        help_text="Print Y nudge in dots (positive shifts down). Irys RFID stock usually needs ~55 at 300 DPI so content lands on the die-cut.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="label_templates"
    )

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    def media_geometry(self):
        return get_media_profile(
            self.media_profile or DEFAULT_MEDIA_PROFILE,
            width_dots=self.width_dots,
            height_dots=self.height_dots,
            dpi=self.dpi or DEFAULT_PRINTER_DPI,
        )

    def apply_media_defaults(self):
        """Resize canvas to the selected paper profile's native size at current DPI."""
        from .media import irys_registration_offset_y

        geo = get_media_profile(
            self.media_profile or DEFAULT_MEDIA_PROFILE,
            dpi=self.dpi or DEFAULT_PRINTER_DPI,
        )
        self.width_dots = geo["width_dots"]
        self.height_dots = geo["height_dots"]
        self.dpi = geo["dpi"]
        if (self.media_profile or DEFAULT_MEDIA_PROFILE) == "irys_standard":
            # New Irys templates start with the die-cut registration nudge.
            if not self.offset_y:
                self.offset_y = irys_registration_offset_y(self.dpi)

    def apply_jewellery_sample_layout(self):
        """Replace fields with the canonical print-accurate Irys jewellery sample."""
        from .media import irys_jewellery_sample_layout

        layout = irys_jewellery_sample_layout(self.dpi or DEFAULT_PRINTER_DPI)
        geo = layout["geometry"]
        self.media_profile = "irys_standard"
        self.dpi = layout["dpi"]
        self.width_dots = layout["width_dots"]
        self.height_dots = layout["height_dots"]
        self.offset_x = layout["offset_x"]
        self.offset_y = layout["offset_y"]
        self.save(
            update_fields=[
                "media_profile",
                "dpi",
                "width_dots",
                "height_dots",
                "offset_x",
                "offset_y",
                "updated_at",
            ]
        )
        self.fields.all().delete()
        for order, row in enumerate(layout["fields"]):
            LabelField.objects.create(
                template=self,
                order=order,
                visible=True,
                static_text="",
                field_key=row["field_key"],
                x=row["x"],
                y=row["y"],
                font_size=row["font_size"],
                bold=row["bold"],
                align=row["align"],
                box_width=row["box_width"],
            )
        return layout

    def rescale_fields_to_dpi(self, new_dpi):
        """Scale every field's x/y/font/box when the printer DPI changes."""
        old = self.dpi or DEFAULT_PRINTER_DPI
        new = int(new_dpi or DEFAULT_PRINTER_DPI)
        if old == new:
            return
        for f in self.fields.all():
            f.x = scale_dot(f.x, old, new)
            f.y = scale_dot(f.y, old, new)
            f.font_size = max(8, scale_dot(f.font_size, old, new))
            f.box_width = max(10, scale_dot(f.box_width, old, new))
            f.save(update_fields=["x", "y", "font_size", "box_width", "updated_at"])
        self.dpi = new
        self.offset_x = scale_dot(self.offset_x, old, new)
        self.offset_y = scale_dot(self.offset_y, old, new)

class LabelField(TimeStampedModel):
    class FieldKey(models.TextChoices):
        # Identity / tracking
        BARCODE_NUMBER = "barcode_number", "PJ number (barcode text)"
        BARCODE_IMAGE = "barcode_image", "Barcode (scannable)"
        REFERENCE_ID = "reference_id", "Item code / SKU"
        PRODUCT_NAME = "product_name", "Product name"
        SUPPLIER_CODE = "supplier_code", "Supplier code"
        SUPPLIER_NAME = "supplier_name", "Supplier name"
        SUBCATEGORY = "subcategory", "Subcategory"
        CATEGORY_CODE = "category_code", "Category code (JW/ST/…)"
        # Metal / stone
        METAL = "metal", "Metal"
        METAL_PURITY = "metal_purity", "Metal purity"
        STONE = "stone", "Stone"
        COLOUR = "colour", "Colour"
        QUALITY = "quality", "Quality"
        WEIGHT = "weight", "Net weight"
        GROSS_WEIGHT = "gross_weight", "Gross weight"
        SIZE = "size", "Size"
        # Price
        PRICE = "price", "Selling price"
        PRICE_RATED = "price_rated", "Selling price × rate"
        CURRENCY = "currency", "Currency"
        COMPANY_NAME = "company_name", "Company name"
        # Design helpers
        STATIC_TEXT = "static_text", "Custom text"
        HORIZONTAL_LINE = "horizontal_line", "Divider line"

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
    font_size = models.PositiveIntegerField(default=18)
    bold = models.BooleanField(default=False)
    align = models.CharField(max_length=1, choices=Align.choices, default=Align.LEFT)
    box_width = models.PositiveIntegerField(default=180, help_text="Text box width in dots — drives ZPL ^FB wrapping/alignment.")
    visible = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.get_field_key_display()} @ ({self.x},{self.y}) on {self.template}"
