"""
Live data health. Read-only queries against iadmin, run when the page loads.

The owner brief is a frozen printout from the 13 Aug restore. This is the
check that looks at whatever the live SQL Server holds right now.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.utils import timezone

MANILA = ZoneInfo("Asia/Manila")

LIVE_INVOICE = """
    ISNULL(A.bstatus, 1) = 1
    AND ISNULL(A.invoice_number, '') <> ''
    AND ISNULL(A.adminapproval_invoicecancle, '') NOT IN ('apply', 'approved', 'approve')
"""

CANCELLED_INVOICE = """
    ISNULL(A.bstatus, 1) = 1
    AND ISNULL(A.invoice_number, '') <> ''
    AND ISNULL(A.adminapproval_invoicecancle, '') IN ('apply', 'approved', 'approve')
"""

MONEY = "TRY_CAST(REPLACE(ISNULL({col}, '0'), ',', '') AS DECIMAL(18,2))"


def build_data_health(query=None) -> dict:
    """
    `query` takes a SELECT and returns a list of dicts. Tests pass a fake.
    The page passes the live MSSQL reader.
    """
    if query is None:
        from apps.core.legacy_mssql import ping_live, select_rows

        ok, where = ping_live()
        if not ok:
            return {
                "ok": False,
                "where": where,
                "checked_at": timezone.localtime(timezone.now()),
                "checks": [],
                "error": where,
            }
        query = select_rows
    else:
        where = "injected"

    checked_at = timezone.localtime(timezone.now())
    checks = [
        _clock(query),
        _books(query),
        _phantom_complete(query),
        _unpaid_gap(query),
        _sold_counts(query),
        _cost_missing(query),
        _ownership(query),
        _transfers(query),
    ]
    return {
        "ok": True,
        "where": where,
        "checked_at": checked_at,
        "checks": checks,
        "error": "",
        "fail_count": sum(1 for c in checks if c["status"] == "fail"),
        "warn_count": sum(1 for c in checks if c["status"] == "warn"),
    }


def _run(query, sql: str):
    try:
        return query(sql), ""
    except Exception as exc:
        return None, str(exc)


def _dec(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _peso(value) -> str:
    amount = _dec(value)
    return f"₱{amount:,.2f}"


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _day(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _check(check_id, title, status, figure, detail, rows=None):
    return {
        "id": check_id,
        "title": title,
        "status": status,
        "figure": figure,
        "detail": detail,
        "rows": rows or [],
    }


def _clock(query):
    rows, err = _run(query, "SELECT GETDATE() AS server_now")
    if err:
        return _check("clock", "Server clock", "error", "Query failed", err)
    server_now = rows[0].get("server_now") if rows else None
    server_day = _day(server_now)
    manila_today = timezone.now().astimezone(MANILA).date()
    if server_day is None:
        return _check("clock", "Server clock", "error", "No time returned", "GETDATE() came back empty.")
    if server_day != manila_today:
        return _check(
            "clock",
            "Server clock is not Manila",
            "fail",
            f"{server_now} vs {manila_today}",
            "Dashboard queries that use GETDATE() describe a different day from "
            "the date the shop is actually on. “Today” and “this month” on iadmin "
            "are computed from this clock.",
        )
    return _check(
        "clock",
        "Server clock matches Manila today",
        "ok",
        str(server_now),
        "The date part of GETDATE() matches Asia/Manila. The hour can still be off.",
    )


def _books(query):
    sql = f"""
        SELECT
            SUM(CASE WHEN {LIVE_INVOICE} THEN 1 ELSE 0 END) AS live_n,
            SUM(CASE WHEN {LIVE_INVOICE} THEN {MONEY.format(col='A.total_price')} ELSE 0 END) AS live_amt,
            SUM(CASE WHEN {CANCELLED_INVOICE} THEN 1 ELSE 0 END) AS cancel_n,
            SUM(CASE WHEN {CANCELLED_INVOICE} THEN {MONEY.format(col='A.total_price')} ELSE 0 END) AS cancel_amt,
            MIN(CASE WHEN {LIVE_INVOICE}
                THEN TRY_CONVERT(date, ISNULL(NULLIF(A.assign_date, ''), A.creationdate)) END) AS first_on,
            MAX(CASE WHEN {LIVE_INVOICE}
                THEN TRY_CONVERT(date, ISNULL(NULLIF(A.assign_date, ''), A.creationdate)) END) AS last_on
        FROM tblProductAssignMaster A
    """
    rows, err = _run(query, sql)
    if err:
        return _check("books", "Invoiced books", "error", "Query failed", err)
    row = rows[0] if rows else {}
    pay_rows, pay_err = _run(query, f"""
        SELECT
            COUNT(*) AS n,
            SUM({MONEY.format(col='paid_amount')}) AS paid
        FROM tblAssignPayment_transaction
        WHERE ISNULL(bstatus, 1) = 1
    """)
    paid = _dec(pay_rows[0].get("paid")) if pay_rows and not pay_err else None
    live_amt = _dec(row.get("live_amt"))
    outstanding = live_amt - paid if paid is not None else None
    figure = (
        f"{_int(row.get('live_n'))} live · {_peso(live_amt)}"
        + (f" · collected {_peso(paid)}" if paid is not None else "")
    )
    detail = (
        f"Window {row.get('first_on')} to {row.get('last_on')}. "
        f"Cancelled {_int(row.get('cancel_n'))} invoices, {_peso(row.get('cancel_amt'))}. "
    )
    if outstanding is not None:
        detail += f"Outstanding on live invoices: {_peso(outstanding)}. "
    if pay_err:
        detail += f"Payments query failed: {pay_err}"
    status = "ok"
    if _int(row.get("live_n")) == 0:
        status = "warn"
        detail += "No live invoices came back — the filter may not match this database."
    return _check("books", "Invoiced books, read now", status, figure, detail.strip())


def _phantom_complete(query):
    sql = f"""
        SELECT TOP 12
            A.nid,
            R.name AS reseller,
            A.assign_date,
            A.invoice_status,
            A.return_status,
            {MONEY.format(col='A.total_price')} AS total_price,
            ISNULL((
                SELECT SUM(TRY_CAST(soldqty AS DECIMAL(18,4)))
                FROM tblProductAssign X
                WHERE X.master_id = A.nid
            ), 0) AS soldqty
        FROM tblProductAssignMaster A
        LEFT JOIN tblResellerMaster R ON R.nid = TRY_CAST(A.reseller_id AS INT)
        WHERE ISNULL(A.bstatus, 1) = 1
          AND ISNULL(A.invoice_number, '') = ''
          AND {MONEY.format(col='A.total_price')} >= 1
          AND (
                LOWER(ISNULL(A.invoice_status, '')) IN ('complete', 'completed')
             OR LOWER(ISNULL(A.return_status, '')) = 'complete'
          )
          AND ISNULL((
                SELECT SUM(TRY_CAST(soldqty AS DECIMAL(18,4)))
                FROM tblProductAssign X
                WHERE X.master_id = A.nid
          ), 0) = 0
        ORDER BY {MONEY.format(col='A.total_price')} DESC
    """
    rows, err = _run(query, sql)
    if err:
        return _check("phantom", "Complete assignments with no invoice", "error", "Query failed", err)
    samples = []
    total = Decimal("0")
    for row in rows or []:
        amount = _dec(row.get("total_price"))
        total += amount
        samples.append({
            "nid": row.get("nid"),
            "reseller": row.get("reseller") or "—",
            "when": row.get("assign_date") or "",
            "amount": _peso(amount),
            "note": f"invoice {row.get('invoice_status') or '—'} · return {row.get('return_status') or '—'} · soldqty 0",
        })
    if samples:
        return _check(
            "phantom",
            "Complete assignments with no invoice and nothing sold",
            "fail",
            f"{len(samples)} shown · {_peso(total)}",
            "These rows are marked complete, carry a peso total, have no invoice number, "
            "and sold quantity is zero. Adding assignment totals will treat them as sales. "
            "Assignment 97 was this pattern on the August restore.",
            samples,
        )
    return _check(
        "phantom",
        "Complete assignments with no invoice and nothing sold",
        "ok",
        "None",
        "No assignment is currently marked complete, uninvoiced, and unsold with a peso total.",
    )


def _unpaid_gap(query):
    honest_sql = f"""
        SELECT COUNT(*) AS n,
               SUM({MONEY.format(col='A.total_price')} - ISNULL(F.paid, 0)) AS balance
        FROM tblProductAssignMaster A
        OUTER APPLY (
            SELECT ISNULL(SUM({MONEY.format(col='FT.paid_amount')}), 0) AS paid
            FROM tblAssignPayment_transaction FT
            WHERE FT.assign_masterid = A.nid
              AND ISNULL(FT.bstatus, 1) = 1
        ) F
        WHERE {LIVE_INVOICE}
          AND {MONEY.format(col='A.total_price')} - ISNULL(F.paid, 0) >= 1
    """
    old_sql = f"""
        SELECT COUNT(*) AS n
        FROM tblProductAssignMaster A
        OUTER APPLY (
            SELECT TOP 1 {MONEY.format(col='T.rem_amount')} AS rem
            FROM tblAssignPayment_transaction T
            WHERE T.assign_masterid = A.nid
              AND ISNULL(T.bstatus, 1) = 1
            ORDER BY T.nid DESC
        ) P
        WHERE {LIVE_INVOICE}
          AND (P.rem IS NULL OR P.rem >= 1)
    """
    honest, err = _run(query, honest_sql)
    if err:
        return _check("unpaid", "Unpaid invoices", "error", "Query failed", err)
    old, old_err = _run(query, old_sql)
    honest_n = _int(honest[0].get("n")) if honest else 0
    balance = _dec(honest[0].get("balance")) if honest else Decimal("0")
    if old_err:
        return _check(
            "unpaid",
            "Unpaid invoices",
            "warn",
            f"{honest_n} unpaid · {_peso(balance)}",
            f"Billed less every payment is {honest_n}. Could not compare the old last-balance method: {old_err}",
        )
    old_n = _int(old[0].get("n")) if old else 0
    gap = abs(honest_n - old_n)
    if gap:
        return _check(
            "unpaid",
            "Unpaid count depends on which balance you trust",
            "fail",
            f"{old_n} old method · {honest_n} billed less payments",
            f"The last rem_amount on the latest payment row counts {old_n}. "
            f"Billed amount less every payment received counts {honest_n}, "
            f"outstanding {_peso(balance)}. The live iadmin tile uses the old method "
            "until the dashboard files are uploaded.",
        )
    return _check(
        "unpaid",
        "Unpaid invoices",
        "ok",
        f"{honest_n} · {_peso(balance)}",
        "The last-balance method and billed-less-payments agree right now.",
    )


def _sold_counts(query):
    sql = """
        SELECT
            SUM(CASE WHEN LOWER(ISNULL(sold_status, '')) IN ('sold', 'complete') THEN 1 ELSE 0 END) AS by_sold_status,
            SUM(CASE WHEN LOWER(ISNULL(item_current_status, '')) IN ('sold', 'complete') THEN 1 ELSE 0 END) AS by_current_status
        FROM tblproduct_detail_master
        WHERE ISNULL(bstatus, 1) = 1
    """
    rows, err = _run(query, sql)
    if err:
        return _check("sold", "Two sold counts", "error", "Query failed", err)
    row = rows[0] if rows else {}
    a = _int(row.get("by_sold_status"))
    b = _int(row.get("by_current_status"))
    if a != b:
        return _check(
            "sold",
            "Two sold counts on the same pieces",
            "fail",
            f"sold_status {a} · item_current_status {b}",
            "sold_status is the field the dashboard uses. item_current_status on the same "
            "rows says a different number. Quote the sold_status figure; the other is unexplained.",
        )
    return _check(
        "sold",
        "Sold counts agree",
        "ok",
        f"{a} pieces",
        "sold_status and item_current_status currently match.",
    )


def _cost_missing(query):
    sql = """
        SELECT
            COUNT(*) AS designs,
            SUM(CASE
                WHEN TRY_CAST(REPLACE(CAST(ISNULL(purchase_price, '') AS varchar(50)), ',', '') AS DECIMAL(18,2))
                     IS NULL
                  OR TRY_CAST(REPLACE(CAST(ISNULL(purchase_price, '') AS varchar(50)), ',', '') AS DECIMAL(18,2)) = 0
                THEN 1 ELSE 0 END) AS no_cost
        FROM tblproduct_master
        WHERE ISNULL(bstatus, 1) = 1
    """
    rows, err = _run(query, sql)
    if err:
        return _check("cost", "Cost on file", "error", "Query failed", err)
    row = rows[0] if rows else {}
    designs = _int(row.get("designs"))
    missing = _int(row.get("no_cost"))
    if designs and missing == designs:
        return _check(
            "cost",
            "No cost price on file",
            "fail",
            f"{missing} of {designs} designs",
            "purchase_price is empty or zero on every design. Gross margin cannot be calculated from this system.",
        )
    if missing:
        return _check(
            "cost",
            "Cost missing on some designs",
            "warn",
            f"{missing} of {designs}",
            "Those designs have no usable purchase_price. Margin on them is not in the database.",
        )
    return _check("cost", "Cost on file", "ok", f"{designs} designs", "purchase_price is present.")


def _ownership(query):
    sql = """
        SELECT
            LOWER(ISNULL(P.PRODUCT_TYPE, 'blank')) AS kind,
            COUNT(*) AS pieces
        FROM tblproduct_detail_master D
        LEFT JOIN tblproduct_master P ON P.nid = TRY_CAST(D.product_masterid AS INT)
        WHERE ISNULL(D.bstatus, 1) = 1
          AND LOWER(ISNULL(D.sold_status, 'pending')) NOT IN ('sold', 'complete')
        GROUP BY LOWER(ISNULL(P.PRODUCT_TYPE, 'blank'))
    """
    rows, err = _run(query, sql)
    if err:
        return _check("ownership", "Who owns the unsold stock", "error", "Query failed", err)
    counts = {str(row.get("kind") or "blank"): _int(row.get("pieces")) for row in rows or []}
    consign = counts.get("consignment", 0)
    purchased = counts.get("purchased", 0)
    other = sum(n for k, n in counts.items() if k not in ("consignment", "purchased"))
    total = consign + purchased + other
    if not total:
        return _check("ownership", "Who owns the unsold stock", "warn", "No unsold pieces", "Nothing came back.")
    share = round(100 * consign / total) if total else 0
    status = "warn" if share >= 50 else "ok"
    detail = (
        f"Consignment {consign:,} · purchased {purchased:,}"
        + (f" · other {other:,}" if other else "")
        + ". Consignment stock is supplier-owned. It is not company capital."
    )
    return _check(
        "ownership",
        "Who owns the unsold stock",
        status,
        f"{share}% consignment · {total:,} unsold pieces",
        detail,
    )


def _transfers(query):
    sql = """
        SELECT
            COUNT(*) AS all_n,
            SUM(CASE WHEN LOWER(ISNULL(return_status, 'pending')) = 'pending' THEN 1 ELSE 0 END) AS pending_n
        FROM tblproduct_transfer
        WHERE ISNULL(bstatus, 1) = 1
    """
    rows, err = _run(query, sql)
    if err:
        return _check("transfers", "Transfer status column", "error", "Query failed", err)
    row = rows[0] if rows else {}
    all_n = _int(row.get("all_n"))
    pending_n = _int(row.get("pending_n"))
    if all_n and pending_n == all_n:
        return _check(
            "transfers",
            "Every transfer still reads pending",
            "fail",
            f"{pending_n} of {all_n}",
            "return_status is never written after a transfer completes, so a count of "
            "pending transfers is a count of every transfer ever made, not loads in transit.",
        )
    if pending_n:
        return _check(
            "transfers",
            "Transfer status column",
            "warn",
            f"{pending_n} pending of {all_n}",
            "Some rows are not pending. Confirm the column is actually maintained before treating that as in-transit.",
        )
    return _check("transfers", "Transfer status column", "ok", "None pending", "No pending transfer rows.")
