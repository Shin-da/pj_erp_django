"""Parse SQL Server INSERT scripts produced by SSMS (stock_rfid_backup.sql)."""

from __future__ import annotations

import re
from pathlib import Path


INSERT_RE = re.compile(r"^INSERT \[dbo\]\.\[(\w+)\] \((.*?)\) VALUES \((.*)\)\s*$")


def split_columns(col_str: str) -> list[str]:
    return [c.strip().strip("[]") for c in col_str.split(",")]


def split_top_level(s: str) -> list[str]:
    """Split a VALUES(...) inner string on top-level commas, respecting
    N'...'-quoted strings (with '' as an escaped quote) and nested parens
    (for CAST(...) expressions)."""
    parts = []
    depth = 0
    in_str = False
    buf = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if in_str:
            if ch == "'":
                if i + 1 < n and s[i + 1] == "'":
                    buf.append("''")
                    i += 2
                    continue
                in_str = False
                buf.append(ch)
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue
        if ch == "'":
            in_str = True
            buf.append(ch)
            i += 1
            continue
        if ch == "(":
            depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch == ")":
            depth -= 1
            buf.append(ch)
            i += 1
            continue
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return parts


def parse_literal(tok: str):
    tok = tok.strip()
    if tok == "NULL":
        return None
    m = re.match(r"^CAST\((.*)\s+AS\s+[\w()0-9, ]+\)$", tok, re.IGNORECASE | re.DOTALL)
    if m:
        return parse_literal(m.group(1).strip())
    if tok.startswith("N'") and tok.endswith("'"):
        return tok[2:-1].replace("''", "'")
    if tok.startswith("'") and tok.endswith("'"):
        return tok[1:-1].replace("''", "'")
    try:
        if re.match(r"^-?\d+$", tok):
            return int(tok)
        return float(tok)
    except ValueError:
        return tok


def detect_encoding(path: Path) -> str:
    raw = path.read_bytes()[:4]
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return "utf-16"
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    return "utf-8"


def parse_dump(path: Path, wanted: set[str], stdout=None) -> dict[str, list[dict]]:
    """Stream a .sql dump and return {table_name: [row dict, ...]} for wanted tables.

    Table names are matched case-insensitively. Only one-row-per-line INSERT
    statements (the SSMS default for this dump) are collected.

    SSMS writes these scripts as UTF-16; opening them as UTF-8 makes every
    INSERT line look like I\\x00N\\x00S\\x00E\\x00R\\x00T and they are all skipped.
    """
    wanted_lower = {w.lower() for w in wanted}
    tables = {name: [] for name in wanted_lower}
    skipped_mismatch = 0
    insert_seen = 0
    insert_matched = 0
    encoding = detect_encoding(path)
    if stdout:
        stdout.write(f"  encoding: {encoding}")
    with open(path, "r", encoding=encoding, errors="replace") as f:
        for line in f:
            line = line.rstrip("\r\n").lstrip("\ufeff")
            if not line.startswith("INSERT"):
                continue
            insert_seen += 1
            m = INSERT_RE.match(line)
            if not m:
                continue
            insert_matched += 1
            table = m.group(1)
            key = table.lower()
            if key not in tables:
                continue
            columns = split_columns(m.group(2))
            raw_values = split_top_level(m.group(3))
            if len(raw_values) != len(columns):
                skipped_mismatch += 1
                continue
            values = [parse_literal(v) for v in raw_values]
            tables[key].append(dict(zip(columns, values)))
    if stdout:
        stdout.write(f"  INSERT lines seen: {insert_seen}, regex matched: {insert_matched}")
        if skipped_mismatch:
            stdout.write(f"  skipped {skipped_mismatch} INSERT(s) with column/value count mismatch")
    return tables
