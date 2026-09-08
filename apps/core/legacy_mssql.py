"""
Live read-only fetch from the legacy iadmin MSSQL server (mssql.tag11.in).

Returns data in exactly the shape apps/core/legacy_sql.py's parse_dump()
produces — {table_name_lowercased: [row dict, ...]}, row dict keys matching
the original SQL Server column names — so apps/core/legacy_import.py's
mapping code works unchanged against either source.

This module only ever runs SELECT statements. It is never given
credentials with more than read access should be necessary, but even if
the configured account can write, nothing here issues anything but SELECT.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import CommandError


def _connect():
    try:
        import pymssql
    except ImportError as exc:
        raise CommandError(
            "pymssql is not installed. Add it to requirements.txt and `pip install -r requirements.txt`."
        ) from exc

    host = getattr(settings, "LEGACY_MSSQL_HOST", "")
    port = getattr(settings, "LEGACY_MSSQL_PORT", "")
    database = getattr(settings, "LEGACY_MSSQL_DB", "")
    user = getattr(settings, "LEGACY_MSSQL_USER", "")
    password = getattr(settings, "LEGACY_MSSQL_PASSWORD", "")

    missing = [
        name for name, val in [
            ("LEGACY_MSSQL_HOST", host),
            ("LEGACY_MSSQL_PORT", port),
            ("LEGACY_MSSQL_DB", database),
            ("LEGACY_MSSQL_USER", user),
            ("LEGACY_MSSQL_PASSWORD", password),
        ] if not val
    ]
    if missing:
        raise CommandError(f"Missing legacy MSSQL settings: {', '.join(missing)}")

    try:
        return pymssql.connect(
            server=host,
            port=int(port),
            user=user,
            password=password,
            database=database,
            timeout=60,
            login_timeout=20,
            as_dict=False,
        )
    except Exception as exc:  # pymssql raises its own OperationalError etc.
        raise CommandError(f"Could not connect to legacy MSSQL at {host}:{port}/{database} — {exc}") from exc


def fetch_live_tables(wanted: set[str], stdout=None) -> dict[str, list[dict]]:
    """SELECT * from every table in `wanted` and return {table.lower(): [row dict, ...]}."""
    conn = _connect()
    tables: dict[str, list[dict]] = {name.lower(): [] for name in wanted}
    try:
        cur = conn.cursor()
        for table in sorted(wanted):
            try:
                cur.execute(f"SELECT * FROM dbo.[{table}]")
            except Exception as exc:
                if stdout:
                    stdout.write(f"  WARNING: could not read {table}: {exc}")
                continue
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
            tables[table.lower()] = [dict(zip(columns, row)) for row in rows]
            if stdout:
                stdout.write(f"  fetched {table}: {len(rows)} rows")
    finally:
        conn.close()
    return tables


def count_live_tables(wanted: set[str]) -> tuple[dict[str, int | None], str | None]:
    """
    COUNT(*) for each table in `wanted`.

    Returns ({table.lower(): count_or_None}, error_message_or_None).
    A per-table None means that specific SELECT failed; a top-level error
    means the connection itself failed.
    """
    counts: dict[str, int | None] = {name.lower(): None for name in wanted}
    try:
        conn = _connect()
    except Exception as exc:  # CommandError from missing settings / connect failure
        return counts, str(exc)

    try:
        cur = conn.cursor()
        for table in sorted(wanted):
            try:
                cur.execute(f"SELECT COUNT(*) FROM dbo.[{table}]")
                counts[table.lower()] = int(cur.fetchone()[0])
            except Exception:
                counts[table.lower()] = None
    finally:
        conn.close()
    return counts, None


def select_rows(sql: str) -> list[dict]:
    """
    Read-only SELECT. Returns rows as dicts with lowercased column names.

    Used by the developer data-health page. Anything that is not a single
    SELECT is refused before it reaches the server.
    """
    stripped = sql.strip().lstrip("(")
    if not stripped.lower().startswith("select"):
        raise CommandError("Data health only runs SELECT statements.")
    if ";" in stripped.rstrip(";"):
        raise CommandError("Data health refuses multi-statement SQL.")

    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        columns = [d[0].lower() for d in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def ping_live() -> tuple[bool, str]:
    """Quick connectivity check. Returns (ok, detail)."""
    try:
        conn = _connect()
    except Exception as exc:
        return False, str(exc)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        host = settings.LEGACY_MSSQL_HOST
        port = settings.LEGACY_MSSQL_PORT
        db = settings.LEGACY_MSSQL_DB
        return True, f"{host}:{port}/{db}"
    except Exception as exc:
        return False, str(exc)
    finally:
        conn.close()
