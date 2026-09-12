"""C2 HTML authz: mutators must match API permission gates."""

from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Employee
from apps.assignment.models import AssignmentMaster, Reseller
from apps.catalogue.models import Category, Currency, ProductMaster
from apps.inventory.models import ProductItem, StockStatus
from apps.locations.models import Location, LocationType


def _static():
    return override_settings(
        DEBUG=True,
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        },
    )


class HtmlPermissionGateTests(TestCase):
    def setUp(self):
        self.viewer = Employee.objects.create_user(
            employee_code="sales1", password="test-pass", first_name="Sales"
        )
        self.vault = Employee.objects.create_user(
            employee_code="vault1", password="test-pass", first_name="Vault"
        )
        for codename, app in (
            ("can_create_invoice", "assignment"),
            ("can_stamp_invoice", "assignment"),
            ("can_process_return", "returns"),
            ("can_manage_labels", "hardware"),
            ("can_print_label", "hardware"),
            ("can_reprint_label", "hardware"),
            ("add_trackersession", "tracker"),
        ):
            perm = Permission.objects.get(codename=codename, content_type__app_label=app)
            self.vault.user_permissions.add(perm)

        cat = Category.objects.create(name="Jewellery", code="JWL")
        cur = Currency.objects.create(code="USD", symbol="$")
        self.loc = Location.objects.create(
            name="Head office", code="HO", location_type=LocationType.HEAD_OFFICE
        )
        product = ProductMaster.objects.create(
            name="Gate Ring", reference_id="G-1", category=cat, currency=cur
        )
        self.item = ProductItem.objects.create(
            barcode="PJGATE1", product=product, location=self.loc, status=StockStatus.PENDING
        )
        self.reseller = Reseller.objects.create(name="Gate Reseller")

    def test_invoice_create_forbidden_without_perm(self):
        self.client.force_login(self.viewer)
        with _static():
            resp = self.client.post(
                reverse("assignment:invoice_create"),
                {
                    "reseller": self.reseller.pk,
                    "item_barcode": ["PJGATE1"],
                    "unit_price": ["10"],
                },
            )
        self.assertEqual(resp.status_code, 403)

    def test_invoice_stamp_forbidden_without_perm(self):
        master = AssignmentMaster.objects.create(
            reseller=self.reseller, created_by=self.vault
        )
        self.client.force_login(self.viewer)
        with _static():
            resp = self.client.post(reverse("assignment:invoice_stamp", kwargs={"pk": master.pk}))
        self.assertEqual(resp.status_code, 403)

    def test_returns_scan_forbidden_without_perm(self):
        self.client.force_login(self.viewer)
        with _static():
            resp = self.client.get(reverse("returns:return_scan"))
        self.assertEqual(resp.status_code, 403)

    def test_returns_process_allowed_with_perm(self):
        self.item.status = StockStatus.ASSIGNED
        self.item.save(update_fields=["status"])
        self.client.force_login(self.vault)
        with _static():
            resp = self.client.post(
                reverse("returns:process_returns"),
                {"barcode": ["PJGATE1"], "outcome": ["RETURN"]},
            )
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, StockStatus.PENDING)

    def test_template_create_forbidden_without_perm(self):
        self.client.force_login(self.viewer)
        with _static():
            resp = self.client.post(
                reverse("hardware:template_create"),
                {"name": "Nope", "category": "JWL"},
            )
        self.assertEqual(resp.status_code, 403)

    def test_print_page_forbidden_without_print_perms(self):
        self.client.force_login(self.viewer)
        with _static():
            resp = self.client.get(reverse("hardware:print_labels"))
        self.assertEqual(resp.status_code, 403)

    def test_tracker_scan_forbidden_without_perm(self):
        self.client.force_login(self.viewer)
        with _static():
            resp = self.client.get(reverse("tracker:scan"))
        self.assertEqual(resp.status_code, 403)

    def test_tracker_scan_allowed_with_perm(self):
        self.client.force_login(self.vault)
        with _static():
            resp = self.client.get(reverse("tracker:scan"))
        self.assertEqual(resp.status_code, 200)
