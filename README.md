# Perfect Jewel ERP — Django rebuild

Replaces `ftp_perfect-jewel-active-sync` (ASP.NET Web Forms / SQL Server, hosted on
infrastructure Perfect Jewel doesn't own). Architecture and rationale in
`REBUILD-ARCHITECTURE-AND-BUDGET.md` (Workspace/ShinTools); full technical
findings this scaffold is built against are in the `perfect-jewel-system-
landscape.md` project doc.

**Work log:** [`PROJECT_WORKLOG.md`](PROJECT_WORKLOG.md) — chronological log of what was
built (from git + Cursor sessions). Append new session entries at the top of
that file; do not rewrite older ones.

**Decision (19 Aug 2026): full rewrite in Django + PostgreSQL, mimicking
`ftp_perfect-jewel-active-sync` (Sonal's iadmin) as the spec, full
parity.** This is a faithful rebuild of what iadmin actually does — same
modules, same workflows, same data model shape, covering everything
currently live in daily use (catalogue, inventory, tracker, transfers,
assignment/invoicing, payments, returns/reserves, and — still to build —
hardware, Tiara sync, HR/attendance, reporting) — fixing the specific,
documented bugs along the way (plaintext passwords, casing-dependent
status columns, no FKs/indexes, the `manage_stock` toggle bug, the
double-return-on-cancel bug, etc.), not a reimagining and not trimmed
down. Confirmed-dead legacy code (orphan pages, root duplicates, unused
asset folders) is skipped; modules that are simply less-used are not.
Other in-house projects (`pj_erp`, `pj_shop`, `pj-accounting`, the OneLive
Excel workflow) are separate concerns and are **not** inputs to this
project's design — do not cross-reference them when extending this
codebase.

## What's actually built

Real, migrated, exercised end-to-end against local PostgreSQL — not just scaffolded:

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
- **`api`** — `/api/v1/` (DRF).
  - **Read (Api-Key):** products, catalogue lookups, locations, items, resellers,
    invoices, returns, tracker sessions, label templates/logs. Mint with
    `create_api_client`. Docs: `/api/v1/schema/`, `/api/v1/docs/`.
  - **Write (Employee Token/Session):** `POST /api/v1/auth/token/` then
    `Authorization: Token …` for invoice create/stamp, returns process,
    photo upload/delete, tracker opening, print-log create — gated by the
    same Django permission codenames as Manage Employee Access.
  Staff HTML remains the primary ERP UI.
- **`inventory`** — `ProductItem` (one row per barcode), with `status` as a
  real `TextChoices` + a server-enforced transition table
  (`transition_status()`) instead of the free-text, casing-dependent
  `sold_status` column that only worked because of SQL Server's
  case-insensitive collation (`INVENTORY-AND-INVOICING.md` §3, §9a.5).
  Location lives here as a real, always-populated FK — no
  `COALESCE(detail, master, default)` fallback needed. `move_to_location()`
  gives every location change a real audit trail entry.
- **`tracker`** — `TrackerSession` / `TrackerScanItem`, opening/closing/check
  modes, real self-referencing FK for closing→opening links (replacing the
  legacy `parent_tracker_ids` delimited-string column).
- **`transfers`** — full `Transfer`/`TransferLine`, from/to location-match
  validation before any write happens, and `execute_return()` — a real
  implementation of the return-transfer feature the legacy system left as
  an empty handler behind a live button (§4.5).
- **`assignment`** — `Reseller`, `DisplaySlot`/`DisplaySlotAllotment` (the
  room-allotment-as-display-slot coupling, made explicit and honestly
  named instead of silently reaching into a hotel-booking table),
  `AssignmentMaster`/`AssignmentLine` with sequence-backed fixed-width
  invoice numbers and a single pricing function
  (`calculate_line_total()`), replacing the two independently-maintained
  calculations that a SQL comment in the legacy SP said had to be kept
  manually in sync.
- **`returns`** — `ReturnRecord` models return/reassign/reserve/sold as one
  direct state transition each, fixing the legacy bug where every outcome
  ran an unconditional `return_product_by_barcode` first and only
  *afterward* re-claimed the item in the same postback — meaning
  "returned" was a real DB state you could observe for a reserved/
  reassigned item in the old system, when it should never have been.
  `ReserveAlert` flags that expiry currently depends on a scheduled job
  existing (`apps.sync`, not yet built) rather than page-visit timing,
  which is what the legacy system actually did.
- **`payments`** — `ResellerPayment`/`SupplierPayment` (one app, two models,
  replacing two near-duplicate legacy page trees that differed only by
  lookup axis) and `InvoiceCancellation.approve()`, which returns each
  item exactly once — the legacy `invoicecancel_approval.aspx.cs` ran a
  *second* physical return per barcode on top of whatever
  `ProductReturn.aspx` had already done for the same items.

**Confirmed in Postgres directly:** 52 real foreign keys, 133 indexes.
The legacy system has 0 and 0 (confirmed by reading `stock_rfid.dacpac`'s
`model.xml` directly — see `IADMIN-SYSTEM-REFERENCE.md` §9b.1).

**End-to-end smoke-tested as one flow, not module by module**: seeded
demo locations/items on the legacy `TESTER-CHEATSHEET.md` scheme
(`PJ-HO-*`/`PJ-SR-*`/`PJ-ADM-*`) → transferred two items HO→SR →
assigned one to a demo reseller and stamped an invoice (`RE000001`) →
recorded a partial payment against it → marked the item sold → cancelled
the invoice and confirmed the item returned to `PENDING` exactly once →
on the second item, ran the RESERVE return outcome and confirmed it
landed on `RESERVED` directly, with no observable transient "returned"
state in between. 11 real audit-log rows resulted, all queryable.

## What's still not built (`hardware`, `sync`, `hr`, `reporting`)

Each has a `models.py` docstring naming the legacy file it replaces and the
specific bugs/findings it needs to address when built — not empty
boilerplate, but no models yet either. These are next, in that order,
matching what's left of `SYSTEM-AUDIT.md` §6's "already working, daily
jewellery path" plus HR/reporting. Read each stub's docstring before
starting that app — they're scoped TODOs with citations, not placeholders.

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
python manage.py import_mssql_snapshot --flush   # real FTP snapshot into the current catalog
# python manage.py seed_demo                    # tiny fake barcodes, skip once the snapshot is loaded
python manage.py createsuperuser  # or use employee_code=1001 / changeme123 if the importer created it
python manage.py runserver
```

Two local catalogs (`pj_erp_dev` / `pj_erp_prod`) and how to switch: [`DATABASE.md`](DATABASE.md).

## Media files (product photos) on Render

WhiteNoise only serves collected static assets. Uploads live in object storage:

1. Create a **Cloudflare R2** (or S3) bucket with public read (or a custom domain).
2. Set the `AWS_*` vars from `.env.example` on the Render service.
3. Deploy, then from a machine that has the local `media/` tree and the same env:

   ```bash
   python manage.py upload_local_media
   ```

   That copies existing keys (`product_images/…`, etc.) so DB rows keep working.
   New admin uploads go straight to the bucket.

Brand logos under `static/core/img/brand/` are static files (git + `collectstatic`), not media.

## Next steps

1. Build `hardware` (per-device scanner auth, replacing the one hardcoded
   shared secret), `sync` (Tiara/Irys, with `replace=true` and the
   `nid<15` limit both removed by construction), `hr` (EmployeeProfile PII
   separate from `accounts.Employee`, attendance reporting), `reporting`
   (openpyxl/pandas exports).
2. Confirm the exact end date of the current hosting subscription — the
   real deadline for the ASP.NET bridge-hosting decision.
3. Reload the snapshot after a new MSSQL dump: `python manage.py import_mssql_snapshot --flush` then `clone_prod_to_dev --yes`. See `DATABASE.md`.
4. Build the actual UI (Django templates + admin is all that exists today
   — no custom views/forms yet beyond login/home).
