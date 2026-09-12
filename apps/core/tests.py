"""
Regression tests for the iadmin -> Django mirror.

These cover the failure mode found on 9 Sep 2026: this system had been
syncing from the live iadmin SQL Server daily and still showed 337 pieces
sold against iadmin's 577, and parked 6,646 pieces at Head Office that
iadmin had spread across Main Vault, Pullout and the showroom. Nothing
errored — the importer was deliberately skipping status and location on
update, and reading location off the shared product master instead of the
per-barcode row. Both are cheap to get wrong again, hence these.

Run without a local Postgres:

    python manage.py test apps.core --settings=config.settings_sqlite
"""

import io
from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.legacy_import import LegacyImporter
from apps.inventory.models import ProductItem, StockStatus
from apps.tracker.models import ScanMode, TrackerSession
from apps.transfers.models import Transfer, TransferStatus


def legacy_tables(*, sold_status="pending", detail_location=None, master_location=2):
    """A miniature stock_rfid: two locations, one design, one barcode."""
    return {
        "tblcompany_locations": [
            {"nid": 1, "location_code": "HO", "location_name": "Head Office"},
            {"nid": 2, "location_code": "MV", "location_name": "Main Vault"},
            {"nid": 3, "location_code": "SR", "location_name": "Show Room"},
        ],
        "tbljewellery_type": [{"nid": 1, "jewellery_name": "Jewellery", "code": "JW"}],
        "tblproduct_master": [
            {
                "nid": 10,
                "product_Name": "Test ring",
                "reference_id": "REF10",
                "company_locationid": master_location,
                "selling_price": "1000",
            }
        ],
        "tblproduct_detail_master": [
            {
                "nid": 100,
                "product_masterid": 10,
                "barcode_number": "PJ00001",
                "sold_status": sold_status,
                "company_locationid": detail_location,
            }
        ],
    }


def run_import(tables, **kwargs):
    LegacyImporter(stdout=io.StringIO()).run(tables, **kwargs)


class ItemStateRefreshTests(TestCase):
    def test_resync_moves_a_sold_piece_out_of_company_stock(self):
        run_import(legacy_tables(sold_status="pending"))
        self.assertEqual(ProductItem.objects.get(barcode="PJ00001").status, StockStatus.PENDING)

        run_import(legacy_tables(sold_status="sold"))
        self.assertEqual(ProductItem.objects.get(barcode="PJ00001").status, StockStatus.SOLD)

    def test_resync_follows_a_transfer_to_a_new_location(self):
        run_import(legacy_tables(detail_location=2))
        self.assertEqual(ProductItem.objects.get(barcode="PJ00001").location.code, "MV")

        run_import(legacy_tables(detail_location=3))
        self.assertEqual(ProductItem.objects.get(barcode="PJ00001").location.code, "SR")

    def test_per_barcode_location_beats_the_shared_product_master(self):
        """
        The master row is the *design*, shared by every piece of that
        style. Reading it as the item's location is what put thousands of
        pieces at Head Office that were physically elsewhere.
        """
        run_import(legacy_tables(master_location=1, detail_location=2))
        self.assertEqual(ProductItem.objects.get(barcode="PJ00001").location.code, "MV")

    def test_master_location_is_still_the_fallback(self):
        run_import(legacy_tables(master_location=3, detail_location=None))
        self.assertEqual(ProductItem.objects.get(barcode="PJ00001").location.code, "SR")

    def test_preserve_local_state_opts_out(self):
        """The setting for the day Perfect Jewel works here instead of in iadmin."""
        run_import(legacy_tables(sold_status="pending"))
        run_import(legacy_tables(sold_status="sold"), preserve_local_state=True)
        self.assertEqual(ProductItem.objects.get(barcode="PJ00001").status, StockStatus.PENDING)


class TransferImportTests(TestCase):
    def test_finished_transfer_does_not_import_as_pending(self):
        """
        `return_status` defaults to 'pending' and nothing in iadmin ever
        moves it, because return-transfer was never implemented there.
        Importing those as PENDING is what makes a dashboard claim
        hundreds of transfers are in progress when none are.
        """
        tables = legacy_tables(detail_location=3)
        tables["tblproduct_transfer"] = [
            {
                "nid": 5,
                "transferid_from": 2,
                "transferid_to": 3,
                "total_count": 1,
                "transfer_date": datetime(2026, 9, 8),
                "return_status": "pending",
                "bstatus": 1,
                "active_status": "active",
            }
        ]
        tables["tblproduct_transfer_details"] = [
            {"nid": 50, "tranfer_id": 5, "pjnumber": "PJ00001", "return_status": "pending", "bstatus": 1}
        ]
        run_import(tables)

        transfer = Transfer.objects.get(legacy_id=5)
        self.assertEqual(transfer.status, TransferStatus.COMPLETE)
        self.assertEqual(Transfer.objects.filter(status=TransferStatus.PENDING).count(), 0)
        self.assertEqual(transfer.lines.count(), 1)
        # History only — the item is where _import_items put it, not moved again.
        self.assertEqual(ProductItem.objects.get(barcode="PJ00001").location.code, "SR")

    def test_transfer_import_is_idempotent(self):
        tables = legacy_tables(detail_location=3)
        tables["tblproduct_transfer"] = [
            {
                "nid": 5, "transferid_from": 2, "transferid_to": 3,
                "transfer_date": datetime(2026, 9, 8), "return_status": "pending", "bstatus": 1,
            }
        ]
        tables["tblproduct_transfer_details"] = [
            {"nid": 50, "tranfer_id": 5, "pjnumber": "PJ00001", "bstatus": 1}
        ]
        run_import(tables)
        run_import(tables)
        self.assertEqual(Transfer.objects.count(), 1)
        self.assertEqual(Transfer.objects.get(legacy_id=5).lines.count(), 1)


class TrackerImportTests(TestCase):
    def _tables(self):
        tables = legacy_tables(detail_location=2)
        tables["tblproduct_tracker"] = [
            {
                "nid": 7,
                "scan_string": "SN012",
                "scan_index": 12,
                "items_qty": 1,
                "scan_date": datetime(2026, 9, 8, 14, 30),
                "scan_mode": "opening",
                "workflow_mode": "scan_only",
                "from_location_id": 2,
                "bstatus": 1,
            },
            {
                "nid": 8,
                "scan_index": 13,
                "items_qty": 1,
                "scan_date": datetime(2026, 9, 8, 16, 0),
                "workflow_mode": "transfer_only",
                "from_location_id": 2,
                "to_location_id": 3,
                "parent_tracker_ids": "7",
                "bstatus": 1,
            },
        ]
        tables["tblproduct_tracker_itemsdeatils"] = [
            {"nid": 70, "trackerid": 7, "pjnumber": "PJ00001", "pjnumber_location": "company", "bstatus": 1}
        ]
        return tables

    def test_sessions_and_scan_lines_import(self):
        run_import(self._tables())
        self.assertEqual(TrackerSession.objects.count(), 2)
        opening = TrackerSession.objects.get(legacy_id=7)
        self.assertEqual(opening.mode, ScanMode.OPENING)
        self.assertEqual(opening.location.code, "MV")
        self.assertEqual(opening.scan_items.count(), 1)

    def test_transfer_only_session_is_flagged(self):
        run_import(self._tables())
        session = TrackerSession.objects.get(legacy_id=8)
        self.assertEqual(session.mode, ScanMode.TRANSFER)
        self.assertTrue(session.is_transfer)
        self.assertEqual(session.parent_session_id, TrackerSession.objects.get(legacy_id=7).pk)

    def test_scan_is_dated_when_it_happened_not_when_it_was_imported(self):
        """`scans today` on the dashboard is worthless if every scan lands on import day."""
        run_import(self._tables())
        created = timezone.localtime(TrackerSession.objects.get(legacy_id=7).created_at)
        self.assertEqual(created.date(), datetime(2026, 9, 8).date())
        self.assertEqual(created.hour, 14)

    def test_hidden_sessions_are_skipped(self):
        tables = self._tables()
        tables["tblproduct_tracker"][1]["bstatus"] = 0
        run_import(tables)
        self.assertEqual(TrackerSession.objects.count(), 1)

    def test_tracker_import_is_idempotent(self):
        run_import(self._tables())
        run_import(self._tables())
        self.assertEqual(TrackerSession.objects.count(), 2)
        self.assertEqual(TrackerSession.objects.get(legacy_id=7).scan_items.count(), 1)


class DataHealthTests(TestCase):
    def test_phantom_complete_and_unpaid_gap_come_from_the_query(self):
        from apps.core.data_health import build_data_health

        def query(sql):
            text = " ".join(sql.split()).lower()
            if "getdate()" in text:
                return [{"server_now": datetime(2026, 9, 9, 3, 0)}]
            if "live_n" in text:
                return [{
                    "live_n": 2, "live_amt": 1000, "cancel_n": 1, "cancel_amt": 100,
                    "first_on": "2026-07-10", "last_on": "2026-09-08",
                }]
            if "from tblassignpayment_transaction" in text and "paid" in text and "rem_amount" not in text and "assign_masterid" not in text:
                return [{"n": 1, "paid": 400}]
            if "soldqty" in text:
                return [{
                    "nid": 97, "reseller": "JUNNEL", "assign_date": "2026-08-05",
                    "invoice_status": "complete", "return_status": "complete",
                    "total_price": 7547626, "soldqty": 0,
                }]
            if "rem_amount" in text:
                return [{"n": 1}]
            if "billed less" in text or "f.paid" in text:
                return [{"n": 3, "balance": 600}]
            if "sold_status" in text and "item_current_status" in text:
                return [{"by_sold_status": 10, "by_current_status": 4}]
            if "purchase_price" in text:
                return [{"designs": 5, "no_cost": 5}]
            if "product_type" in text:
                return [{"kind": "consignment", "pieces": 8}, {"kind": "purchased", "pieces": 2}]
            if "tblproduct_transfer" in text:
                return [{"all_n": 4, "pending_n": 4}]
            raise AssertionError(sql)

        report = build_data_health(query=query)
        self.assertTrue(report["ok"])
        by_id = {c["id"]: c for c in report["checks"]}
        self.assertEqual(by_id["phantom"]["status"], "fail")
        self.assertEqual(by_id["phantom"]["rows"][0]["nid"], 97)
        self.assertEqual(by_id["unpaid"]["status"], "fail")
        self.assertEqual(by_id["sold"]["status"], "fail")
        self.assertEqual(by_id["cost"]["status"], "fail")
        self.assertEqual(by_id["transfers"]["status"], "fail")

    def test_ordinary_staff_are_refused_health(self):
        user = get_user_model().objects.create_user(
            employee_code="staffhealth", password="x", is_developer=False,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("core:data_health"))
        self.assertEqual(response.status_code, 403)


class OwnerBriefTests(TestCase):
    def test_developer_sees_the_confirmed_figures(self):
        user = get_user_model().objects.create_user(
            employee_code="devbrief", password="x", is_developer=True,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("core:owner_brief"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "₱9,090,832")
        self.assertContains(response, "₱7,547,626")
        self.assertContains(response, "Assignment 97")
        self.assertNotContains(response, "₱2,000/day")

    def test_ordinary_staff_are_refused(self):
        user = get_user_model().objects.create_user(
            employee_code="staffbrief", password="x", is_developer=False,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("core:owner_brief"))
        self.assertEqual(response.status_code, 403)


class DashboardTests(TestCase):
    def _login(self):
        run_import(legacy_tables(detail_location=2))
        user = get_user_model().objects.get(employee_code="1001")
        self.client.force_login(user)

    def test_home_renders(self):
        self._login()
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Main Vault")

    def test_stock_money_is_labelled_as_list_price(self):
        """
        These are sums of the catalogue's selling_price. Shown bare beside
        a piece count they read as inventory valuation or as revenue, and
        they are neither.
        """
        self._login()
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "at list price")

    def test_empty_assigned_tile_does_not_claim_nothing_is_out(self):
        """
        Perfect Jewel moves stock to a reseller's room by transfer, not by
        assignment, so this tile sits at zero while hundreds of pieces are
        off site. "None currently out" was a wrong answer to a question
        the owner actually asks.
        """
        self._login()
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "None currently out")
        self.assertContains(response, "see By location")
