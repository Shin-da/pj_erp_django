from decimal import Decimal
from io import BytesIO

from django.test import TestCase
from openpyxl import Workbook

from apps.catalogue.datafile import metal_family, parse_rows, apply_rows as apply_datafile
from apps.catalogue.intake import infer_metal_name, parse_jewellery_workbook
from apps.catalogue.models import strip_dflt_prefix
from apps.locations.models import Location, LocationType


class IntakeParseTests(TestCase):
    def test_dflt_prefix_is_not_a_metal(self):
        self.assertEqual(strip_dflt_prefix("DFLT - 18K"), "18K")
        self.assertEqual(infer_metal_name("", "DFLT - 18K"), "Gold")
        self.assertEqual(infer_metal_name("", "DFLT - PT900"), "Platinum")
        self.assertEqual(infer_metal_name("", ""), "")

    def test_catches_jewellery_excel_header_on_row_2(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Jewellery Excel"
        ws.append(["title"] * 5)
        ws.append(["supplier", "Supplier_product_code", "Supplier_nick_name", "Metal Purity", "PJNUMBER"])
        ws.append(["YZC", "Z-R4442", "YZC1", "DFLT - 18K", "PJ24881"])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        parsed = parse_jewellery_workbook(buf)
        self.assertEqual(parsed.errors, [])
        self.assertEqual(len(parsed.rows), 1)
        self.assertEqual(parsed.rows[0].pj, "PJ24881")
        self.assertEqual(parsed.rows[0].purity, "DFLT - 18K")
        self.assertEqual(parsed.rows[0].reference, "Z-R4442")


class IntakeApplyTests(TestCase):
    def test_blank_metal_name_stores_gold_not_silver(self):
        from apps.catalogue.intake import IntakeRow, apply_rows

        Location.objects.create(name="Head office", code="HO", location_type=LocationType.HEAD_OFFICE)
        row = IntakeRow(
            row_number=3,
            pj="PJ24881",
            reference="Z-R4442",
            owner="YZC1",
            supplier="YZC",
            subcategory="RN",
            metal_name="",
            purity="DFLT - 18K",
            weight="1.58",
            actual_price=Decimal("239.4"),
            currency="USD",
            rate=Decimal("63"),
            payment_type="markuptype1",
            markup=Decimal("10"),
            markup_amount=None,
            size="",
            diamond_weight="",
        )
        report = apply_rows([row], Location.objects.get(code="HO"))
        self.assertEqual(report["created"], 1)
        item = Location.objects.get(code="HO").items.get(barcode="PJ24881")
        self.assertEqual(item.product.metal.name, "Gold")
        self.assertEqual(item.product.purity.name, "18K")
        self.assertEqual(item.product.gold_weight, "1.58")
        self.assertEqual(item.product.selling_price, Decimal("215.46"))


class DatafileSyncTests(TestCase):
    def test_blank_metal_type_uses_purity_not_silver(self):
        self.assertEqual(metal_family("", "18K+3G"), "Gold")
        self.assertEqual(metal_family("SL", "925"), "Silver")

    def test_sheet_purity_replaces_wrong_metal(self):
        from apps.catalogue.models import Category, Currency, Metal, ProductMaster
        from apps.inventory.models import ProductItem
        from apps.locations.models import Location, LocationType

        cat = Category.objects.create(name="Jewellery", code="JW")
        cur = Currency.objects.create(code="USD")
        silver = Metal.objects.create(name="Silver")
        loc = Location.objects.create(name="Head office", code="HO", location_type=LocationType.HEAD_OFFICE)
        product = ProductMaster.objects.create(
            name="YZC1", reference_id="BR0704-1-3G", category=cat, currency=cur, metal=silver,
        )
        ProductItem.objects.create(barcode="PJ25073", product=product, location=loc)
        csv_text = (
            "RFID Tag,Metal Type,Metal Purity,Net Weight,Metal Weight,Gross Weight\n"
            "PJ25073,,18K+3G,9.05g,,\n"
        )
        report = apply_datafile(parse_rows(csv_text))
        product.refresh_from_db()
        self.assertEqual(report["updated"], 1)
        self.assertEqual(product.metal.name, "Gold")
        self.assertEqual(product.purity.name, "18K+3G")
        self.assertEqual(product.net_weight, Decimal("9.05"))
