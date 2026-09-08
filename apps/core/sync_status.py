"""
Dev-facing comparison of live MSSQL stock_rfid vs local Postgres catalogs.

Used by the Sync Status page. Count-only — never writes.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg2
from django.conf import settings

from apps.core.legacy_mssql import count_live_tables, ping_live


# (label, mssql table, postgres table, match_mode)
# match_mode:
#   exact  — counts must match for "synced"
#   soft   — local catalog may be ahead (seed/local rows); behind is a problem
#   items  — MSSQL may have 1 unimportable row (missing product/barcode)
COMPARE_ROWS = (
    ("Products", "tblproduct_master", "catalogue_productmaster", "exact"),
    ("Items", "tblproduct_detail_master", "inventory_productitem", "items"),
    ("Locations", "tblcompany_locations", "locations_location", "soft"),
    ("Categories", "tbljewellery_type", "catalogue_category", "soft"),
    ("Suppliers", "tblvendor_type", "catalogue_supplier", "exact"),
    ("Resellers", "tblResellerMaster", "assignment_reseller", "exact"),
    ("Invoices", "tblProductAssignMaster", "assignment_assignmentmaster", "exact"),
    ("Invoice lines", "tblProductAssign", "assignment_assignmentline", "exact"),
    ("Reseller payments", "tblAssignPayment_transaction", "payments_resellerpayment", "exact"),
)

MSSQL_TABLES = {mssql for _, mssql, _, _ in COMPARE_ROWS}
PG_TABLES = {pg for _, _, pg, _ in COMPARE_ROWS}


@dataclass
class EntityRow:
    label: str
    mssql: int | None
    prod: int | None
    dev: int | None
    match_mode: str = "exact"

    @property
    def prod_delta(self) -> int | None:
        if self.mssql is None or self.prod is None:
            return None
        return self.prod - self.mssql

    @property
    def dev_delta(self) -> int | None:
        if self.mssql is None or self.dev is None:
            return None
        return self.dev - self.mssql

    def _ok(self, delta: int | None) -> bool:
        if delta is None:
            return False
        if self.match_mode == "soft":
            return delta >= 0
        if self.match_mode == "items":
            return delta in (0, -1)
        return delta == 0

    @property
    def prod_ok(self) -> bool:
        return self._ok(self.prod_delta)

    @property
    def dev_ok(self) -> bool:
        return self._ok(self.dev_delta)

    @property
    def affects_overall(self) -> bool:
        return self.match_mode in ("exact", "items")


def _pg_connect(dbname: str):
    cfg = settings.DATABASES["default"]
    return psycopg2.connect(
        dbname=dbname,
        user=cfg["USER"],
        password=cfg["PASSWORD"],
        host=cfg["HOST"],
        port=cfg["PORT"],
        connect_timeout=5,
    )


def ping_postgres(dbname: str) -> tuple[bool, str]:
    try:
        conn = _pg_connect(dbname)
    except Exception as exc:
        return False, str(exc)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        host = settings.DATABASES["default"]["HOST"]
        port = settings.DATABASES["default"]["PORT"]
        return True, f"{host}:{port}/{dbname}"
    except Exception as exc:
        return False, str(exc)
    finally:
        conn.close()


def count_postgres_tables(dbname: str) -> tuple[dict[str, int | None], str | None]:
    counts: dict[str, int | None] = {t: None for t in PG_TABLES}
    try:
        conn = _pg_connect(dbname)
    except Exception as exc:
        return counts, str(exc)
    try:
        cur = conn.cursor()
        for table in PG_TABLES:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                counts[table] = int(cur.fetchone()[0])
            except Exception:
                conn.rollback()
                counts[table] = None
    finally:
        conn.close()
    return counts, None


def build_sync_report() -> dict:
    mssql_ok, mssql_detail = ping_live()
    prod_name = settings.DB_NAME_BY_PROFILE["prod"]
    dev_name = settings.DB_NAME_BY_PROFILE["dev"]
    prod_ok, prod_detail = ping_postgres(prod_name)
    dev_ok, dev_detail = ping_postgres(dev_name)

    mssql_counts: dict[str, int | None] = {}
    mssql_err = None
    if mssql_ok:
        mssql_counts, mssql_err = count_live_tables(MSSQL_TABLES)

    prod_counts: dict[str, int | None] = {}
    prod_err = None
    if prod_ok:
        prod_counts, prod_err = count_postgres_tables(prod_name)

    dev_counts: dict[str, int | None] = {}
    dev_err = None
    if dev_ok:
        dev_counts, dev_err = count_postgres_tables(dev_name)

    rows = [
        EntityRow(
            label=label,
            mssql=mssql_counts.get(mssql.lower()),
            prod=prod_counts.get(pg),
            dev=dev_counts.get(pg),
            match_mode=mode,
        )
        for label, mssql, pg, mode in COMPARE_ROWS
    ]

    core = [r for r in rows if r.affects_overall and r.mssql is not None]
    prod_synced = bool(core) and all(r.prod_ok for r in core)
    dev_synced = bool(core) and all(r.dev_ok for r in core)
    prod_dev_match = bool(rows) and all(
        r.prod is not None and r.dev is not None and r.prod == r.dev for r in rows
    )

    return {
        "mssql": {
            "ok": mssql_ok and not mssql_err,
            "detail": mssql_err or mssql_detail,
            "host": settings.LEGACY_MSSQL_HOST,
            "port": settings.LEGACY_MSSQL_PORT,
            "name": settings.LEGACY_MSSQL_DB,
            "user": settings.LEGACY_MSSQL_USER,
        },
        "prod": {
            "ok": prod_ok and not prod_err,
            "detail": prod_err or prod_detail,
            "name": prod_name,
            "synced": prod_synced,
        },
        "dev": {
            "ok": dev_ok and not dev_err,
            "detail": dev_err or dev_detail,
            "name": dev_name,
            "synced": dev_synced,
        },
        "active_profile": settings.DB_PROFILE,
        "active_name": settings.DATABASES["default"]["NAME"],
        "rows": rows,
        "prod_dev_match": prod_dev_match,
        "overall_synced": prod_synced and dev_synced,
    }
