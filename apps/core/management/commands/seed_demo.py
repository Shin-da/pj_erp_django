"""
Seeds a small demo dataset mirroring the legacy system's own
`TESTER-CHEATSHEET.md` scheme (PJ-HO-*, PJ-SR-*, PJ-ADM-* barcodes across
Head Office / Show Room / Admin Room), so the new schema can be exercised
end-to-end without waiting on a full data migration from `stock_rfid_dev`.

Idempotent — safe to re-run.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.locations.models import Location, LocationType
from apps.catalogue.models import Category, Currency, Metal, Purity, ProductMaster
from apps.inventory.models import ProductItem, StockStatus


class Command(BaseCommand):
    help = "Seed demo locations/catalogue/inventory data for local development."

    @transaction.atomic
    def handle(self, *args, **options):
        ho, _ = Location.objects.get_or_create(
            code="HO", defaults={"name": "Head Office", "location_type": LocationType.HEAD_OFFICE}
        )
        sr, _ = Location.objects.get_or_create(
            code="SR", defaults={"name": "Show Room", "location_type": LocationType.SHOWROOM}
        )
        adm, _ = Location.objects.get_or_create(
            code="ADM", defaults={"name": "Admin Room", "location_type": LocationType.BRANCH}
        )

        category, _ = Category.objects.get_or_create(name="Jewellery", defaults={"code": "JW"})
        currency, _ = Currency.objects.get_or_create(code="PHP", defaults={"symbol": "₱"})
        metal, _ = Metal.objects.get_or_create(name="Gold")
        purity, _ = Purity.objects.get_or_create(metal=metal, name="18K")

        product, _ = ProductMaster.objects.get_or_create(
            reference_id="DEMO-RING-01",
            defaults={
                "name": "Demo Solitaire Ring",
                "category": category,
                "currency": currency,
                "metal": metal,
                "purity": purity,
                "selling_price": Decimal("45000.00"),
                "net_weight": Decimal("3.200"),
            },
        )

        created = 0
        for prefix, location, count in [("PJ-HO", ho, 10), ("PJ-SR", sr, 6), ("PJ-ADM", adm, 4)]:
            for i in range(1, count + 1):
                barcode = f"{prefix}-{i:02d}"
                _, was_created = ProductItem.objects.get_or_create(
                    barcode=barcode,
                    defaults={"product": product, "location": location, "status": StockStatus.PENDING},
                )
                created += int(was_created)

        self.stdout.write(self.style.SUCCESS(
            f"Seed complete. Locations: HO/SR/ADM. Product: {product}. New items created: {created}."
        ))
