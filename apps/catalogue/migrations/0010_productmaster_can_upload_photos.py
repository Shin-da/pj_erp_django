# Generated manually for catalogue.can_upload_photos (+ ensure can_intake_stock is registered)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0009_product_intake_history"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="productmaster",
            options={
                "ordering": ["name"],
                "permissions": [
                    (
                        "can_intake_stock",
                        "Can bring in stock via Excel upload or one-piece intake (C2 fix — "
                        "SYSTEM-AUDIT-2026-09-11.md)",
                    ),
                    (
                        "can_upload_photos",
                        "Can upload design photos by PJ / barcode (separate from stock intake)",
                    ),
                ],
            },
        ),
    ]
