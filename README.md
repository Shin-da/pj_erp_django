# Perfect Jewel ERP — Django rebuild

Replaces `ftp_perfect-jewel-active-sync` (ASP.NET Web Forms / SQL Server, hosted on
infrastructure Perfect Jewel doesn't own). Architecture and rationale in
`REBUILD-ARCHITECTURE-AND-BUDGET.md` (Workspace/ShinTools); full technical
findings this scaffold is built against are in the `perfect-jewel-system-
landscape.md` project doc.

**Decision (19 Aug 2026): full rewrite in Django + PostgreSQL**, not a
port of `pj_erp` (the working Flask/SQLite prototype). `pj_erp` stays a
reference for proven domain logic (its schema, RBAC enforcement, and
atomic-invoice pattern are all worth re-checking against as each Django
app gets built) but is not the codebase going forward.

## What's actually built (this pass)

Real, migrated, exercised against local PostgreSQL — not just scaffolded:

- **`core`** — `TimeStampedModel`, `SoftDeleteModel`, and a real persisted
  `AuditLogEntry` (the legacy tracker audit trail lived only in ViewState
  and never survived the request — confirmed in `DATA-FLOW-VERIFICATION.md`).
- **`accounts`** — custom `Employee` user model, login by `employee_code`,
  Django's built-in hashed-password + Group/Permission system replacing
  `tblemployee`'s plaintext password column and the CSV-role-matched-with-
  `LIKE` permission check that only 87 of ~130 legacy pages actually enforced.
- **`locations`** — `Location` with a real `location_type` enum, replacing
  the hardcoded `'HO'` string comparisons and the two-independent-flags
  (`bstatus` / `active_status`) inconsistency documented in
  `INVENTORY-AND-INVOICING.md` §2.
- **`catalogue`** — `ProductMaster` + lookup tables, with real
  `DecimalField`/`DateField` types replacing the legacy schema's
  `nvarchar`-for-everything pattern (confirmed schema-wide in `_schema_columns.txt`).
  Location is deliberately **not** a field here — see `inventory` below.
- **`inventory`** — `ProductItem` (one row per barcode), with `status` as a
  real `TextChoices` + a server-enforced transition table
  (`transition_status()` in `apps/inventory/models.py`) instead of the
  free-text, casing-dependent `sold_status` column that only worked because
  of SQL Server's case-insensitive collation (`INVENTORY-AND-INVOICING.md`
  §3, §9a.5). Location lives here as a real, always-populated FK — no
  `COALESCE(detail, master, default)` fallback needed, because there's
  nothing to fall back from.
- **`tracker`** — `TrackerSession` / `TrackerScanItem`, opening/closing/check
  modes, real self-referencing FK for closing→opening links (replacing the
  legacy `parent_tracker_ids` delimited-string column).
- **`transfers`** — minimal header model only (`Transfer`), just enough for
  `tracker` to link a scan session to the transfer it produced.

Verified end-to-end in a shell session (see git log / commit message for
the exact commands): seeded demo locations/items mirroring the legacy
`TESTER-CHEATSHEET.md` scheme (`PJ-HO-*`, `PJ-SR-*`, `PJ-ADM-*`), created a
real `TrackerSession`, exercised `transition_status()` including a
correctly-rejected invalid transition, and confirmed a real `AuditLogEntry`
row was written — not appended to a ViewState blob that vanishes on
postback.

**Confirmed in Postgres directly:** 29 real foreign keys, 96 indexes.
The legacy system has 0 and 0 (confirmed by reading `stock_rfid.dacpac`'s
`model.xml` directly — see `IADMIN-SYSTEM-REFERENCE.md` §9b.1).

## What's stubbed, not built (`assignment`, `payments`, `returns`,
`hardware`, `sync`, `hr`, `reporting`)

Each has a `models.py` docstring naming the legacy file it replaces and the
specific bugs/findings it needs to address when built — not empty
boilerplate, but no models yet either. Per `REBUILD-ARCHITECTURE-AND-BUDGET.md`
§5's own sequencing: `inventory` + `tracker` first because they're the
modules with the most recent, best-understood logic (the `active-sync`
branch's location-enforcement fixes are the blueprint). Read each stub's
docstring before starting that app — they're not placeholders, they're
scoped TODOs with citations.

## Legal note

No `.env`, no real secret keys, and nothing from the legacy codebase was
copied verbatim into this project — models were written from the
*documented behavior* (audit docs + reading the legacy source), not by
porting code. `System-Handover-and-IP-Assignment.docx` is still an
unsigned draft as of this writing; see the project doc §2 before reusing
anything more literal than a design pattern from the legacy source.

## Running locally

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit if your local Postgres differs
python manage.py migrate
python manage.py seed_demo        # optional demo data
python manage.py createsuperuser  # or use employee_code=1001 / changeme123 from the seed session
python manage.py runserver
```

## Next steps (from REBUILD-ARCHITECTURE-AND-BUDGET.md §5, still open)

1. Confirm the exact end date of the current hosting subscription — the
   real deadline for the ASP.NET bridge-hosting decision.
2. Seed this schema from a real export of `stock_rfid_dev` instead of demo
   data, once a migration/ETL script exists (not yet written).
3. Build out `transfers` fully (line items, from/destination routing,
   fixing the legacy return-transfer gap), then `assignment`/`invoicing`.
