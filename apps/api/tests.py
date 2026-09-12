from decimal import Decimal
from uuid import uuid4

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.api.models import ApiClient
from apps.assignment.models import AssignmentLine, AssignmentMaster, InvoiceStatus, Reseller
from apps.catalogue.models import Category, Currency, ProductMaster
from apps.hardware.models import LabelPrintLog, LabelTemplate
from apps.inventory.models import ProductItem, StockStatus
from apps.locations.models import Location, LocationType
from apps.returns.models import ReserveAlert, ReturnOutcome, ReturnRecord
from apps.tracker.models import ScanMode, TrackerSession


API_RF = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.authentication.ApiKeyAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.api.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}


@override_settings(REST_FRAMEWORK=API_RF)
class ProductApiPhase0Tests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Jewellery", code="JW")
        self.currency = Currency.objects.create(code="USD", symbol="$")
        self.client_row, self.raw_key = ApiClient.create_with_key("phase0-tests")
        self.api = APIClient()
        self.list_url = reverse("api:product-list")

    def _auth(self):
        self.api.credentials(HTTP_AUTHORIZATION=f"Api-Key {self.raw_key}")

    def test_list_requires_api_key(self):
        response = self.api.get(self.list_url)
        self.assertEqual(response.status_code, 401)

    def test_list_rejects_invalid_key(self):
        self.api.credentials(HTTP_AUTHORIZATION="Api-Key not-a-real-key")
        response = self.api.get(self.list_url)
        self.assertEqual(response.status_code, 401)

    def test_list_ok_with_valid_key(self):
        ProductMaster.objects.create(
            name="Ring A",
            reference_id="REF-A",
            category=self.category,
            currency=self.currency,
            is_active=True,
        )
        self._auth()
        response = self.api.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("results", body)
        self.assertIn("count", body)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["reference_id"], "REF-A")

    def test_retrieve_by_pk_not_reference_id(self):
        product = ProductMaster.objects.create(
            name="Ring B",
            reference_id="LOOKS-LIKE-REF",
            category=self.category,
            currency=self.currency,
            is_active=True,
        )
        self._auth()
        by_pk = self.api.get(reverse("api:product-detail", kwargs={"pk": product.pk}))
        self.assertEqual(by_pk.status_code, 200)
        self.assertEqual(by_pk.json()["id"], product.pk)

        by_ref_path = self.api.get(
            reverse("api:product-detail", kwargs={"pk": "LOOKS-LIKE-REF"})
        )
        self.assertEqual(by_ref_path.status_code, 404)

    def test_duplicate_reference_id_filter_returns_both(self):
        ProductMaster.objects.create(
            name="Dup 1",
            reference_id="DUP-REF",
            category=self.category,
            currency=self.currency,
            is_active=True,
        )
        ProductMaster.objects.create(
            name="Dup 2",
            reference_id="DUP-REF",
            category=self.category,
            currency=self.currency,
            is_active=True,
        )
        self._auth()
        response = self.api.get(self.list_url, {"reference_id": "DUP-REF"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 2)

    def test_pagination_page_size_capped(self):
        for i in range(5):
            ProductMaster.objects.create(
                name=f"Item {i}",
                reference_id=f"P-{i}",
                category=self.category,
                currency=self.currency,
                is_active=True,
            )
        self._auth()
        response = self.api.get(self.list_url, {"page_size": 2})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["results"]), 2)
        self.assertEqual(body["count"], 5)
        self.assertIsNotNone(body["next"])

        huge = self.api.get(self.list_url, {"page_size": 9999})
        self.assertEqual(huge.status_code, 200)
        self.assertLessEqual(len(huge.json()["results"]), 200)

    def test_inactive_products_excluded(self):
        ProductMaster.objects.create(
            name="Hidden",
            reference_id="HIDE",
            category=self.category,
            currency=self.currency,
            is_active=False,
        )
        self._auth()
        response = self.api.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_revoked_key_rejected(self):
        self.client_row.is_active = False
        self.client_row.save(update_fields=["is_active"])
        self._auth()
        response = self.api.get(self.list_url)
        self.assertEqual(response.status_code, 401)

    def test_schema_requires_api_key(self):
        response = self.api.get(reverse("api:schema"))
        self.assertEqual(response.status_code, 401)
        self._auth()
        ok = self.api.get(reverse("api:schema"))
        self.assertEqual(ok.status_code, 200)


@override_settings(REST_FRAMEWORK=API_RF)
class Phase1ReadApiTests(TestCase):
    def setUp(self):
        _, self.raw_key = ApiClient.create_with_key("phase1-tests")
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f"Api-Key {self.raw_key}")

        self.category = Category.objects.create(name="Jewellery", code="JWL")
        self.currency = Currency.objects.create(code="USD", symbol="$")
        self.location = Location.objects.create(
            name="Head office", code="HO", location_type=LocationType.HEAD_OFFICE
        )
        self.product = ProductMaster.objects.create(
            name="Phase1 Ring",
            reference_id="P1-REF",
            category=self.category,
            currency=self.currency,
            selling_price=Decimal("100.00"),
        )
        self.item = ProductItem.objects.create(
            barcode="PJPHASE1",
            product=self.product,
            location=self.location,
            status=StockStatus.PENDING,
        )
        self.reseller = Reseller.objects.create(name="Acme Reseller", reference_code="ACM")
        self.invoice = AssignmentMaster.objects.create(
            reseller=self.reseller,
            invoice_status=InvoiceStatus.DRAFT,
        )
        AssignmentLine.objects.create(
            master=self.invoice,
            item=self.item,
            unit_price=Decimal("100.00"),
        )

    def test_phase1_collections_require_auth(self):
        bare = APIClient()
        for name in (
            "api:item-list",
            "api:location-list",
            "api:invoice-list",
            "api:reseller-list",
            "api:return-list",
            "api:tracker-session-list",
            "api:label-template-list",
            "api:category-list",
        ):
            with self.subTest(name=name):
                self.assertEqual(bare.get(reverse(name)).status_code, 401)

    def test_items_list_and_retrieve_by_barcode(self):
        listed = self.api.get(reverse("api:item-list"), {"status": "PENDING"})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)

        detail = self.api.get(
            reverse("api:item-detail", kwargs={"barcode": "PJPHASE1"})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["location_code"], "HO")
        self.assertEqual(detail.json()["product_reference_id"], "P1-REF")
        self.assertNotIn("purchase_price", detail.json())

    def test_locations_retrieve_by_code(self):
        detail = self.api.get(reverse("api:location-detail", kwargs={"code": "HO"}))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["name"], "Head office")

    def test_invoices_list_and_retrieve_includes_lines(self):
        listed = self.api.get(reverse("api:invoice-list"))
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)
        self.assertNotIn("lines", listed.json()["results"][0])

        detail = self.api.get(
            reverse("api:invoice-detail", kwargs={"pk": self.invoice.pk})
        )
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["reseller_name"], "Acme Reseller")
        self.assertEqual(len(body["lines"]), 1)
        self.assertEqual(body["lines"][0]["barcode"], "PJPHASE1")
        self.assertNotIn("commission_value", body["lines"][0])

    def test_resellers_and_categories(self):
        resellers = self.api.get(reverse("api:reseller-list"), {"q": "Acme"})
        self.assertEqual(resellers.status_code, 200)
        self.assertEqual(resellers.json()["count"], 1)

        cats = self.api.get(reverse("api:category-list"))
        self.assertEqual(cats.status_code, 200)
        self.assertGreaterEqual(cats.json()["count"], 1)

    def test_returns_and_reserve_alerts(self):
        ReturnRecord.objects.create(item=self.item, outcome=ReturnOutcome.RETURN)
        ReserveAlert.objects.create(
            item=self.item,
            reseller=self.reseller,
            expires_at="2099-01-01T00:00:00Z",
        )
        returns = self.api.get(reverse("api:return-list"), {"barcode": "PJPHASE1"})
        self.assertEqual(returns.status_code, 200)
        self.assertEqual(returns.json()["count"], 1)

        alerts = self.api.get(reverse("api:reserve-alert-list"), {"open": "true"})
        self.assertEqual(alerts.status_code, 200)
        self.assertEqual(alerts.json()["count"], 1)

    def test_tracker_sessions(self):
        session = TrackerSession.objects.create(
            location=self.location,
            mode=ScanMode.OPENING,
            item_count=0,
        )
        listed = self.api.get(reverse("api:tracker-session-list"))
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)

        detail = self.api.get(
            reverse(
                "api:tracker-session-detail",
                kwargs={"scan_index": session.scan_index},
            )
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["location_code"], "HO")
        self.assertIn("scans", detail.json())

    def test_label_templates_and_print_logs(self):
        template = LabelTemplate.objects.create(name="Phase1 Jewellery", category="JWL")
        LabelPrintLog.objects.create(
            batch_id=uuid4(),
            barcode="PJPHASE1",
            template=template,
            template_name=template.name,
            status="success",
        )
        templates = self.api.get(reverse("api:label-template-list"), {"category": "JWL"})
        self.assertEqual(templates.status_code, 200)
        self.assertGreaterEqual(templates.json()["count"], 1)
        names = {row["name"] for row in templates.json()["results"]}
        self.assertIn("Phase1 Jewellery", names)

        detail = self.api.get(
            reverse("api:label-template-detail", kwargs={"pk": template.pk})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertIn("fields", detail.json())

        logs = self.api.get(
            reverse("api:label-print-log-list"), {"barcode": "PJPHASE1"}
        )
        self.assertEqual(logs.status_code, 200)
        self.assertEqual(logs.json()["count"], 1)
