"""Read-only schema for the data workbench. SELECT only. Never writes."""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.db import connection

from apps.core.data_map import DJANGO_TABLES, LEGACY_TABLES, SYNCED

CACHE_SECONDS = 180

# Joins the reports and sync actually use. "trap" means the same integer
# is a different name depending on which lookup you open.
LOOSE_JOINS = (
    {"from_table": "tblproduct_master", "from_col": "category", "to_table": "tbljewellery_type", "to_col": "nid", "kind": "used", "note": "Type of jewellery"},
    {"from_table": "tblproduct_master", "from_col": "vendor_id", "to_table": "tblvendor_type", "to_col": "nid", "kind": "used", "note": "Supplier"},
    {"from_table": "tblproduct_master", "from_col": "company_locationid", "to_table": "tblcompany_locations", "to_col": "nid", "kind": "used", "note": "Location on the design"},
    {"from_table": "tblproduct_detail_master", "from_col": "product_masterid", "to_table": "tblproduct_master", "to_col": "nid", "kind": "used", "note": "Piece belongs to a design"},
    {"from_table": "tbljewellery_metal_details", "from_col": "product_id", "to_table": "tblproduct_master", "to_col": "nid", "kind": "used", "note": "Weight row for a design"},
    {"from_table": "tbljewellery_stone_details", "from_col": "product_id", "to_table": "tblproduct_master", "to_col": "nid", "kind": "used", "note": "Stone row for a design"},
    {"from_table": "tbljewellery_stone_details", "from_col": "stone_subcat_id", "to_table": "tblstone_sub_category", "to_col": "nid", "kind": "used", "note": "Stone subcategory"},
    {"from_table": "tblpurity_country_mgmt", "from_col": "purity_id", "to_table": "tblMetalpurity_master", "to_col": "nid", "kind": "used", "note": "Purity half of the combo"},
    {"from_table": "tblpurity_country_mgmt", "from_col": "country_id", "to_table": "tblmetalcountry_master", "to_col": "nid", "kind": "used", "note": "Country half of the combo"},
    {"from_table": "tblProductAssignMaster", "from_col": "reseller_id", "to_table": "tblResellerMaster", "to_col": "nid", "kind": "used", "note": "Invoice customer"},
    {"from_table": "tblProductAssignMaster", "from_col": "reseller_locationid", "to_table": "tblreseller_location", "to_col": "nid", "kind": "used", "note": "Customer location"},
    {"from_table": "tblProductAssign", "from_col": "master_id", "to_table": "tblProductAssignMaster", "to_col": "nid", "kind": "used", "note": "Line on an invoice"},
    {"from_table": "tblProductAssign", "from_col": "barcode_nid", "to_table": "tblproduct_detail_master", "to_col": "nid", "kind": "used", "note": "Piece ids stored as a list, not a real key"},
    {"from_table": "tblAssignPayment_transaction", "from_col": "assign_masterid", "to_table": "tblProductAssignMaster", "to_col": "nid", "kind": "used", "note": "Payment against an invoice"},
    {"from_table": "tbljewellery_metal_details", "from_col": "metal_id", "to_table": "tblmetalcountry_master", "to_col": "nid", "kind": "trap", "note": "Same 1 can mean Silver here"},
    {"from_table": "tbljewellery_metal_details", "from_col": "metal_purity_id", "to_table": "tblMetalpurity_master", "to_col": "nid", "kind": "trap", "note": "Same 1 can mean 24K here"},
    {"from_table": "tbljewellery_metal_details", "from_col": "metal_purity_id", "to_table": "tblpurity_country_mgmt", "to_col": "nid", "kind": "trap", "note": "Same 1 can mean 18K-Japan Gold here"},
)

# Invoice line column names seen in the wild. The workbench attaches whichever exists.
ASSIGN_LINE_COLS = ("master_id", "assignmaster_id", "assign_masterid", "productassignmaster_id")

GROUPS = (
    ("piece", "Piece of jewellery", ("product", "inventory_productitem", "catalogue_product")),
    ("metal", "Metal, purity, stone", ("metal", "purity", "stone", "karat")),
    ("invoice", "Invoices and payments", ("assign", "payment", "reseller", "invoice")),
    ("lookup", "Lookups", ("location", "vendor", "category", "currency", "company", "jewellery_type")),
    ("people", "Staff and login", ("employee", "admin", "auth_", "accounts_")),
    ("other", "Everything else", ()),
)


def _key(name: str) -> str:
    return (name or "").lower()


def _notes_for(store: str) -> dict[str, dict]:
    rows = LEGACY_TABLES if store == "mssql" else DJANGO_TABLES
    return {_key(row["name"]): row for row in rows}


def _synced_names() -> set[str]:
    names = set()
    for _label, legacy, django, _how in SYNCED:
        names.add(_key(legacy.split(".")[0]))
        names.add(_key(django))
    return names


def _group_for(name: str) -> str:
    n = _key(name)
    for gid, _label, needles in GROUPS:
        if gid == "other":
            continue
        if any(bit in n for bit in needles):
            return gid
    return "other"


def _group_label(gid: str) -> str:
    for key, label, _needles in GROUPS:
        if key == gid:
            return label
    return "Everything else"


def _annotate_columns(table_name: str, columns: list[dict], pk: list[str], joins: list[dict]) -> list[dict]:
    pk_set = {_key(c) for c in pk}
    by_col: dict[str, list[dict]] = {}
    for join in joins:
        if _key(join["from_table"]) == _key(table_name):
            by_col.setdefault(_key(join["from_col"]), []).append(join)
    out = []
    for col in columns:
        name = col["name"]
        flags = []
        if _key(name) in pk_set or (not pk and _key(name) == "nid"):
            flags.append("key")
        if _key(name) in ("id",) and "key" not in flags and pk_set == {"id"}:
            flags.append("key")
        attached = by_col.get(_key(name), [])
        if any(j["kind"] == "trap" for j in attached):
            flags.append("trap")
        elif attached:
            flags.append("join")
        elif _key(name).endswith("_id") or _key(name) in {"category", "reseller", "vendor_id"}:
            flags.append("maybe")
        out.append({**col, "flags": flags, "joins": attached})
    return out


def _shape_tables(store: str, raw_tables: list[dict], fks: list[dict]) -> dict:
    notes = _notes_for(store)
    synced = _synced_names()
    loose = [dict(j) for j in LOOSE_JOINS] if store == "mssql" else []
    # Attach invoice-line joins only when those columns exist.
    by_name = {_key(t["name"]): t for t in raw_tables}
    if store == "mssql":
        line = by_name.get("tblproductassign")
        if line:
            colnames = {_key(c["name"]) for c in line["columns"]}
            for col in ASSIGN_LINE_COLS:
                if col in colnames:
                    loose.append({
                        "from_table": "tblProductAssign",
                        "from_col": col,
                        "to_table": "tblProductAssignMaster",
                        "to_col": "nid",
                        "kind": "used",
                        "note": "Invoice line → invoice header",
                    })
                    break

    edges = []
    for fk in fks:
        edges.append({
            "from_table": fk["from_table"],
            "from_col": fk["from_col"],
            "to_table": fk["to_table"],
            "to_col": fk["to_col"],
            "kind": "fk",
            "note": "Enforced by the database",
        })
    edges.extend(loose)

    def _has_col(table: str, col: str) -> bool:
        raw = by_name.get(_key(table))
        if not raw:
            return False
        return any(_key(c["name"]) == _key(col) for c in raw["columns"])

    edges = [e for e in edges if _has_col(e["from_table"], e["from_col"])]
    seen = set()
    unique = []
    for edge in edges:
        key = (_key(edge["from_table"]), _key(edge["from_col"]), _key(edge["to_table"]), _key(edge["to_col"]), edge["kind"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(edge)
    edges = unique
    edges_known = [e for e in edges if e["kind"] != "fk"]

    def edges_from(name: str) -> list[dict]:
        return [e for e in edges if _key(e["from_table"]) == _key(name)]

    def edges_to(name: str) -> list[dict]:
        return [e for e in edges if _key(e["to_table"]) == _key(name)]

    tables = []
    for raw in raw_tables:
        name = raw["name"]
        note = notes.get(_key(name), {})
        pk = raw.get("pk") or []
        if not pk and any(_key(c["name"]) == "nid" for c in raw["columns"]):
            pk = ["nid"]
        outgoing = edges_from(name)
        incoming = edges_to(name)
        tables.append({
            "name": name,
            "rows": raw.get("rows"),
            "pk": pk,
            "holds": note.get("holds", ""),
            "group": _group_for(name),
            "known": bool(note),
            "synced": _key(name) in synced or _key(name.split(".")[0]) in synced,
            "columns": _annotate_columns(name, raw["columns"], pk, outgoing),
            "outgoing": outgoing,
            "incoming": incoming,
        })

    tables.sort(key=lambda t: (0 if t["known"] else 1, t["name"].lower()))
    groups = []
    for gid, label, _needles in GROUPS:
        members = [t for t in tables if t["group"] == gid]
        if members:
            groups.append({"id": gid, "label": label, "tables": members})

    fk_count = sum(1 for e in edges if e["kind"] == "fk")
    return {
        "tables": tables,
        "groups": groups,
        "fk_count": fk_count,
        "loose_count": len(edges_known) if store == "mssql" else 0,
        "table_count": len(tables),
    }


def _mssql_catalog() -> dict:
    from apps.core.legacy_mssql import _connect

    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT t.name,
                   SUM(CASE WHEN p.index_id IN (0, 1) THEN p.rows ELSE 0 END)
            FROM sys.tables t
            LEFT JOIN sys.partitions p ON p.object_id = t.object_id
            WHERE t.is_ms_shipped = 0
            GROUP BY t.name
            """
        )
        counts = {row[0]: int(row[1] or 0) for row in cur.fetchall()}

        cur.execute(
            """
            SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                   IS_NULLABLE, ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo'
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
        )
        cols: dict[str, list[dict]] = {}
        for table, col, dtype, length, nullable, _pos in cur.fetchall():
            type_name = dtype or ""
            if length and dtype in ("varchar", "nvarchar", "char", "nchar"):
                type_name = f"{dtype}({length})"
            cols.setdefault(table, []).append({
                "name": col,
                "type": type_name,
                "nullable": (nullable or "").upper() == "YES",
            })

        cur.execute(
            """
            SELECT ku.TABLE_NAME, ku.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
              ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
             AND tc.TABLE_SCHEMA = ku.TABLE_SCHEMA
            WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
              AND tc.TABLE_SCHEMA = 'dbo'
            ORDER BY ku.TABLE_NAME, ku.ORDINAL_POSITION
            """
        )
        pks: dict[str, list[str]] = {}
        for table, col in cur.fetchall():
            pks.setdefault(table, []).append(col)

        cur.execute(
            """
            SELECT OBJECT_NAME(fk.parent_object_id),
                   COL_NAME(fc.parent_object_id, fc.parent_column_id),
                   OBJECT_NAME(fk.referenced_object_id),
                   COL_NAME(fc.referenced_object_id, fc.referenced_column_id)
            FROM sys.foreign_keys fk
            JOIN sys.foreign_key_columns fc ON fk.object_id = fc.constraint_object_id
            """
        )
        fks = [
            {"from_table": a, "from_col": b, "to_table": c, "to_col": d}
            for a, b, c, d in cur.fetchall()
            if a and c
        ]
    finally:
        conn.close()

    raw = []
    for name, columns in cols.items():
        raw.append({
            "name": name,
            "rows": counts.get(name),
            "pk": pks.get(name, []),
            "columns": columns,
        })
    shaped = _shape_tables("mssql", raw, fks)
    host = getattr(settings, "LEGACY_MSSQL_HOST", "")
    db = getattr(settings, "LEGACY_MSSQL_DB", "")
    return {
        "id": "mssql",
        "title": "Live iadmin",
        "kind": "SQL Server",
        "where": f"{host} / {db}",
        "ok": True,
        "error": "",
        "read_only": True,
        **shaped,
    }


def _postgres_catalog() -> dict:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, GREATEST(c.reltuples, 0)::bigint
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
            """
        )
        counts = {row[0]: int(row[1] or 0) for row in cur.fetchall()}

        cur.execute(
            """
            SELECT table_name, column_name, data_type, character_maximum_length,
                   is_nullable, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """
        )
        cols: dict[str, list[dict]] = {}
        for table, col, dtype, length, nullable, _pos in cur.fetchall():
            type_name = dtype or ""
            if length and dtype in ("character varying", "character"):
                type_name = f"{dtype}({length})"
            cols.setdefault(table, []).append({
                "name": col,
                "type": type_name,
                "nullable": (nullable or "").upper() == "YES",
            })

        cur.execute(
            """
            SELECT ku.table_name, ku.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage ku
              ON tc.constraint_name = ku.constraint_name
             AND tc.table_schema = ku.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = 'public'
            ORDER BY ku.table_name, ku.ordinal_position
            """
        )
        pks: dict[str, list[str]] = {}
        for table, col in cur.fetchall():
            pks.setdefault(table, []).append(col)

        cur.execute(
            """
            SELECT kcu.table_name, kcu.column_name, ccu.table_name, ccu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
            """
        )
        fks = [
            {"from_table": a, "from_col": b, "to_table": c, "to_col": d}
            for a, b, c, d in cur.fetchall()
            if a and c
        ]

    raw = []
    for name, columns in cols.items():
        raw.append({
            "name": name,
            "rows": counts.get(name),
            "pk": pks.get(name, []),
            "columns": columns,
        })
    shaped = _shape_tables("django", raw, fks)
    return {
        "id": "django",
        "title": "Django on this computer",
        "kind": "Postgres",
        "where": f"{settings.DB_PROFILE} / {settings.DATABASES['default']['NAME']}",
        "ok": True,
        "error": "",
        "read_only": True,
        **shaped,
    }


def load_store(store: str, refresh: bool = False) -> dict:
    store = "django" if store == "django" else "mssql"
    key = f"schema-browser:{store}:{getattr(settings, 'DB_PROFILE', '')}"
    if not refresh:
        cached = cache.get(key)
        if cached:
            return cached
    try:
        payload = _mssql_catalog() if store == "mssql" else _postgres_catalog()
    except Exception as exc:
        payload = {
            "id": store,
            "title": "Live iadmin" if store == "mssql" else "Django on this computer",
            "kind": "SQL Server" if store == "mssql" else "Postgres",
            "where": "",
            "ok": False,
            "error": str(exc),
            "read_only": True,
            "tables": [],
            "groups": [],
            "fk_count": 0,
            "loose_count": 0,
            "table_count": 0,
        }
    else:
        cache.set(key, payload, CACHE_SECONDS)
    return payload


def pick_table(store_payload: dict, wanted: str) -> dict | None:
    tables = store_payload.get("tables") or []
    if not tables:
        return None
    if wanted:
        for table in tables:
            if _key(table["name"]) == _key(wanted):
                return table
    for preferred in ("tblproduct_master", "catalogue_productmaster"):
        for table in tables:
            if _key(table["name"]) == preferred:
                return table
    known = next((t for t in tables if t["known"]), None)
    return known or tables[0]
