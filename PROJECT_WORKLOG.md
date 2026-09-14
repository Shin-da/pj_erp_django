# Project work log — Perfect Jewel ERP (Django rebuild)

Living log of work on this repo (`pj_erp_django` / `pj-erp`).  
**There was no prior work log** — this file was created 2026-09-07 from git/`main` history plus Cursor session notes, so later sessions can **append** instead of rewriting.

| | |
|---|---|
| Repo | https://github.com/Shin-da/pj_erp_django |
| Branch | `main` |
| Deploy | DigitalOcean App Platform (+ Spaces); see `DEPLOY-DIGITALOCEAN.md` |
| Related docs | `OWNER-ONE-PAGER.md` (plain-language status, both systems), `README.md` (what’s built), `DATABASE.md` / `DATABASE-GUIDE.md` |
| Sibling spec | https://github.com/Shin-da/ftp_perfect-jewel-active-sync (`PROJECT_WORKLOG.md` there) |

---

## How to append (future sessions)

1. **Do not rewrite** older entries unless correcting a factual error — add a short note under that entry instead.
2. Add a new block at the **top of “Session / phase entries”** (newest first), using this template:

```markdown
### YYYY-MM-DD — Short title

- **Source:** Cursor chat “…” / git `abcdef1`… / manual
- **Goal:** …
- **Done:**
  - …
- **Follow-ups / open:**
  - …
- **Commits (if any):** `hash` — message
```

3. Optionally bump the **“Current focus”** one-liner below.
4. After meaningful merges, you can refresh the **Commit appendix** with:
   `git log --reverse --format="%h|%ad|%s" --date=short`

---

## Current focus

**Photo pipeline live:** Spaces `perfect-jewel-media` (nyc3) linked (~1019 ProductImages). Keep App env on that bucket/keys. Floating uploads + history ready after deploy.

---

## Snapshot (what this project is)

Full rewrite of Perfect Jewel’s daily RFID / iadmin-style ERP in **Django + PostgreSQL**, replacing ASP.NET Web Forms / SQL Server (`ftp_perfect-jewel-active-sync`). Decision recorded **2026-08-19**: parity rebuild with known legacy bugs fixed, not a greenfield redesign.

Major modules touched in commits so far: core, accounts, locations, catalogue, inventory, tracker, transfers, assignment/invoicing, payments, returns, hardware (Zebra / Irys tags), legacy MSSQL sync + cron webhook, product images, global search, Render deploy.

---

## Session / phase entries

### 2026-09-14 — Floating photo uploads + full upload history

- **Source:** Cursor chat — upload before PJ exists; history with complete details
- **Goal:** Photo staff can upload when free even if stock has not created the PJ yet; keep a full audit of every upload.
- **Done:**
  - `PhotoUploadBatch` + `StagedProductImage` (WAITING / ATTACHED / SKIPPED / FAILED / DISCARDED).
  - Unknown PJ / no-code files are **floating** (not rejected); auto-claim when barcode or PJ `reference_id` is created.
  - Manual assign / discard on the upload page; `/products/photos/history/` (+ batch detail).
  - API `products/photos/` stages unknown codes too (`staged` in response).
  - Tests: stage unknown + claim on `ProductItem` create.
- **Follow-ups / open:**
  - App Platform env must use `perfect-jewel-media` + `nyc3` Spaces keys (regenerated).
  - ~365 Spaces files still unmatched (PJ not in live stock) — can stage as floating later.
- **Commits (if any):** _(filled after commit)_

### 2026-09-14 — Harden product photo upload (UI + API)

- **Source:** Cursor chat “lets enhance it making it solid”
- **Goal:** Make `/products/photos/` and the write API solid enough for photo-team volume (not just one-off desk uploads).
- **Done:**
  - Drag-drop + sequential one-file AJAX uploads (avoids giant multipart timeouts on App Platform).
  - Gallery: set primary, delete one/all, live refresh without full page reload; bulk unmatched CSV download.
  - `ProductImage.thumbnail` + `display_url`; list/detail pages prefer thumbs; settings `PRODUCT_PHOTO_THUMB_*`.
  - API: `match_filename` bulk, set-primary, delete-all; serializer now includes `id` + `thumb_url`.
  - `backfill_product_image_thumbs` management command for images imported without thumbs.
  - Tests: AJAX upload, set-primary, bulk_one.
- **Follow-ups / open:**
  - After almarphoto folder import finishes: run `backfill_product_image_thumbs`.
  - Optional later: direct-to-Spaces / presigned uploads; create-unverified from the UI.
- **Commits (if any):** _(pending)_

### 2026-09-14 — Legacy import flush + longer location codes

- **Source:** git uncommitted local work / commit + push
- **Goal:** Unblock legacy stock RFID import when related rows exist; allow longer location codes.
- **Done:**
  - `--flush` now deletes payments, assignments, returns, tracker scans, and transfers before products/suppliers/locations.
  - `Location.code` max length raised 20 → 30, plus migration `0002_alter_location_code`.
- **Follow-ups / open:**
  - None for this fix.
- **Commits (if any):** `c9bbe3a` — Widen location codes and fix legacy import flush order.
  - Note: hash was `fef42e9` pre-rebase onto `a256e48` (AWS_DEFAULT_ACL); rewritten to `c9bbe3a` / work-log record `6cf9650`.

### 2026-09-12 — DigitalOcean App Platform deploy prep

- **Source:** Cursor chat “going to digital ocean now”
- **Goal:** Make the repo deployable on DO App Platform with Spaces (not Render-only).
- **Done:**
  - `DATABASE_URL` (+ `DB_SSLMODE`) in settings; local profile DB when unset.
  - Production HTTPS cookie / HSTS / `CSRF_TRUSTED_ORIGINS` when `DEBUG=False`.
  - `.do/app.yaml`, `DEPLOY-DIGITALOCEAN.md`; start.sh runs `setup_permission_groups` + longer gunicorn timeout.
- **Follow-ups / open:**
  - Create Spaces bucket + App in DO dashboard; set encrypted secrets.
  - After live: staff access, `create_api_client`, optional `upload_local_media`.
- **Commits (if any):** `8a69999` — Prepare DigitalOcean App Platform deploy with Spaces.

- **Source:** Cursor chat “do what we need to do next”
- **Goal:** Close C2 gap — staff HTML must not bypass API permission gates via browser.
- **Done:**
  - `@require_perm` on assignment create/stamp/item-lookup; returns scan/lookup/process; hardware template design mutators; tracker scan/validate/expected-count.
  - Print page: `@require_any_perm(can_print_label, can_reprint_label)`; `print_log` enforces reprint vs first-print separately.
  - Added `require_any_perm` in `accounts/access.py`.
  - Tests in `apps/accounts/tests_html_perms.py`.
- **Follow-ups / open:**
  - Optional: hide nav links for users lacking perms (UX only — server gates are the security).
  - Label template list still login-only (read); fine for now.
- **Commits (if any):** `2fed3a5` — Gate HTML mutators with the same permissions as the API.

### 2026-09-12 — API Phase 2: Employee write endpoints

- **Source:** Cursor chat “commit and push then phase 2”
- **Goal:** Mutating `/api/v1/` surface with Employee auth + same permission codenames as the access map.
- **Done:**
  - `POST /api/v1/auth/token/` (+ revoke); DRF `authtoken`; writes reject Api-Key-only.
  - Writes: returns process, invoice create/stamp, product photo upload/delete, tracker validate + opening session, label print-log create.
  - Shared services: `returns.services.process_return_batch`, `assignment.services.create_invoice` (HTML returns/invoice create call them).
  - Model `Meta.permissions` + migrations for assignment/returns/hardware custom perms.
  - Tests: token auth, Api-Key blocked on writes, invoice/return/tracker/print, 403 without perm (23 API tests).
- **Follow-ups / open:**
  - Deploy migrate + `setup_permission_groups`.
  - Apply `@require_perm` on matching HTML mutators (still login-only in places).
  - Closing/check tracker modes; label template save API.
- **Commits (if any):** `0fa0757` — Add Employee write API with shared invoice/return services.

### 2026-09-12 — API Phase 1: domain read coverage

- **Source:** Cursor chat “Phase 1”
- **Goal:** Expose authenticated read endpoints across ERP domains (not products-only).
- **Done:**
  - Split `apps/api` serializers/views by domain; shared `ApiClientReadMixin`.
  - Resources: categories, currencies, metals, purities, suppliers, locations (by code), items (by barcode), reseller-groups/locations/resellers, invoices (+ lines on retrieve; commissions omitted), returns, reserve-alerts, tracker-sessions (by scan_index + scans on retrieve), label-templates, label-print-logs.
  - Tests for auth gates + list/retrieve/filter smoke across domains (17 API tests).
- **Follow-ups / open:**
  - Phase 2: mutating endpoints + Employee session/token auth + `require_perm`.
  - Optional: ApiClient scopes (prices / invoices).
- **Commits (if any):** `004c86d` — Ship secure /api/v1/ read API (Phase 0-1).

### 2026-09-12 — API Phase 0: secure mount + products read

- **Source:** Cursor chat “start Phase 0” (full API layer program)
- **Goal:** Wire DRF safely: deny-by-default auth, pagination, OpenAPI, fix product lookup, tests — no unauthenticated catalog leak.
- **Done:**
  - Added `djangorestframework` + `drf-spectacular`; `apps.api` in `INSTALLED_APPS`; `REST_FRAMEWORK` defaults (Api-Key only, `IsAuthenticated`, throttle, page size 50 / max 200).
  - Mounted `path("api/v1/", …)`; schema/docs require Api-Key.
  - `ProductViewSet`: explicit auth; detail by `pk`; `reference_id` filter-only (duplicate-safe).
  - Tests: 401 without/invalid/revoked key; 200 list; retrieve-by-pk; dup filter; pagination cap; inactive excluded; schema auth.
- **Follow-ups / open:**
  - Phase 1: read endpoints for inventory, invoices, returns, tracker, hardware.
  - Deploy: `pip install -r requirements.txt` + `migrate` (api.0001 if not applied) + mint a key.
- **Commits (if any):** _(pending)_

### 2026-09-12 — Photo remove + keep full-resolution camera files

- **Source:** Cursor chat (upload photos page follow-ups)
- **Goal:** Let photo staff delete shots for a looked-up PJ; store large camera originals (not downscaled) for Spaces/R2/DO live use; harden bulk upload.
- **Done:**
  - Per-photo remove + Remove all on `/products/photos/?code=…` (deletes DB row + storage object; re-promotes primary).
  - Default `PRODUCT_PHOTO_MAX_WIDTH=0` keeps originals; per-file cap 100&nbsp;MB; higher `DATA_UPLOAD_MAX_MEMORY_SIZE` for bulk.
  - Clearer unmatched/oversized reporting; Spaces example in `.env.example`.
  - Tests for delete and oversized reject.
- **Follow-ups / open:**
  - Raise DO/nginx client body size + timeout for big bulk drops.
  - Optional HEIC support if cameras shoot that by default.
- **Commits (if any):** `042a879` — Allow photo remove and keep full-resolution camera uploads.

### 2026-09-12 — ERP photo upload by PJ / barcode (separate from stock intake)

- **Source:** Cursor chat “check barcode photo upload / implement separate flow”
- **Goal:** Give photo people an ERP screen to attach pictures by PJ/barcode, separate from `/products/add/` stock intake, while keeping the same login/permission system and the same design↔image chain.
- **Done:**
  - Shared helpers in `apps/catalogue/photos.py` (resolve barcode → design, attach uploads, bulk-by-filename).
  - New permission `catalogue.can_upload_photos` (Manage Employee Access + migration `0010`); not auto-granted to Vault Staff baseline — photo staff are dialed in individually.
  - UI `/products/photos/` (`product_photo_upload`): look up PJ, show design + existing gallery, multi-file upload; optional bulk match by PJ in filename.
  - Product list / design / piece pages link to upload when permitted; Add stock / Upload photos buttons gated by their permissions.
  - Tests: forbidden without perm, barcode upload, bulk filename match, unknown code does not create stock.
- **Follow-ups / open:**
  - Run `migrate` + `setup_permission_groups` (no baseline change for photos) and grant `can_upload_photos` to photo employees.
  - Unverified almarphoto → real stock merge still not implemented.
- **Commits (if any):** `3bb63e2` — Add PJ/barcode photo upload separate from stock intake.

### 2026-09-11 — Principal engineer / red-team full-system audit

- **Source:** Cursor chat “Principal Engineer + Red-Team Full-System Audit”
- **Goal:** Determine actual system state from evidence (code, live local Postgres, executed tests), not docs.
- **Done:**
  - Full audit report: [`SYSTEM-AUDIT-2026-09-11.md`](SYSTEM-AUDIT-2026-09-11.md).
  - Executed: `manage.py check` (clean), `manage.py test` (**14 passed**), live constraint/row probes on `pj_erp_prod`, auth smoke tests.
  - Corrected false/stale claims in `README.md`, `apps/accounts/models.py`, `apps/inventory/models.py`; expanded `.env.example`; ignored export xlsx in `.gitignore`.
- **Follow-ups / open (critical):**
  - Sync path still calls `ensure_local_admin` → resets `1001`/`changeme123` — remove + rotate if present on Render.
  - Authz still `@login_required` only on mutators.
  - `reference_id` not unique (160 duplicate groups / 359 rows locally); API lookup unsafe.
  - No `select_for_update`; status CHECK claimed in docs was never in DB.
  - Local `main` **4 commits behind** `origin/main` + large dirty/untracked tree (incl. `apps/api/`).
  - django-q configured but no worker; WeasyPrint used but not in `requirements.txt`.
- **Commits (if any):** none yet

### 2026-09-11 — Product intake template + upload history

- **Source:** Cursor chat; iadmin Product Master `Upload Excel` → `website_product_reference.aspx` + Excel Logs (`excel_log.aspx` / `tblUploadexcel_list`)
- **Goal:** Add stock should offer a downloadable jewellery Excel template, then keep a history of each upload once it lands.
- **Done:**
  - `/products/add/template/` downloads `JewelleryExcelDData.xlsx` — same `Jewellery Excel` sheet, row-2 headers (`PJNUMBER`, `Supplier_product_code`, purity, dates, …).
  - Each Excel drop (and one-piece save) writes `ProductIntakeBatch` + lines. After upload you land on `/products/add/history/<id>/` with the PJ numbers from that file. The add page lists earlier drops.
  - Sheet `purchase_type` / `purchase_date` / `due_date` now store on the design (consignment lots included).
- **Follow-ups / open:**
  - Local check left `PJTESTINTAKE1` in the prod-snapshot catalog (upload 1). Delete if it should not stay.
  - Not on Render until this is committed and deployed. Live iadmin Excel Logs stay on MSSQL.
- **Commits (if any):** none yet

### 2026-09-11 — Product photos on the piece page + has-photos filter

- **Source:** Cursor chat screenshots of `/products/13512/` → `/products/item/PJ6781/` → View design
- **Goal:** Photos should not require hopping Design → barcode → View design. Filter the catalogue to designs that have pictures.
- **Done:**
  - Piece page shows the design’s photo gallery when one exists (same shots as `/products/<id>/`).
  - `/products/` filter **Has photos** / **No photos**, plus a **With photos** summary chip.
- **Follow-ups / open:**
  - `01690755` / `PJ6781` has **no** `ProductImage` row — gem placeholder is correct until that photo is imported. ~1,060 of ~8,733 designs have photos locally.
- **Commits (if any):** none yet

### 2026-09-11 — Consignment lot details page (practice copy)

- **Source:** Cursor chat screenshot of `Consignment_productdetails.aspx?productid=4561`
- **Goal:** Same chrome as the due list: show which design this is, due date, and where each piece sits. Return stays a real stock action.
- **Done:** Work is on `ftp_perfect-jewel-active-sync` (not this Django repo): header + white panel; reference / style / supplier / purchase / due; free-sold-reserved-assigned counts; empty states; confirm before return. Header hides when opened from consignment payment (`?embed=1`). Removed the leftover `openBarcodePopup()` call that was not defined on this page.
- **Follow-ups / open:**
  - Not FTP’d to live. Upload `ConsignmentDue.cs` with this page.
  - Return still uses the existing `product_return_bybarcode` SP.
- **Commits (if any):** none yet

### 2026-09-11 — iadmin dashboard UX + consignment list (practice copy)

- **Source:** Cursor chat “enhance the ui/ux of the dashboard… add or enhance consignment_alert_master.aspx”
- **Goal:** Owner/floor-first dashboard with numbers that do not double-count; consignment list filter matches rows.
- **Done:** Work is on `ftp_perfect-jewel-active-sync` (not this Django repo): company stock excludes reserved pieces; unpaid is peso outstanding; cancelled invoices left out of sales KPIs; consignment chips `?due=` filter in SQL. Dashboard uses the same white panel as the consignment list. Stock KPIs were stuck at 0 (`NOT EXISTS` inside `SUM`); fixed with a reserve `LEFT JOIN`. Rechecked live: 8,472 tagged = 7,862 company + 610 sold.
- **Follow-ups / open:**
  - Not FTP’d to live. Upload `ConsignmentDue.cs` first.
  - Django catalogue still needs a re-sync for dates (see entry below).
- **Commits (if any):** none yet

### 2026-09-11 — Guide to both databases (ERD + page map)

- **Source:** Cursor chat “absorb the two databases… tables on what page… ERD for both”
- **Goal:** One readable map of live iadmin `stock_rfid` and Django Postgres — not just catalog-switch notes.
- **Done:**
  - New [`DATABASE-GUIDE.md`](DATABASE-GUIDE.md): design vs piece vs invoice, mermaid ERDs, iadmin and Django page → table maps (including multi-table pages), name translation, metal-id trap, sync direction.
  - Pointer in the FTP tree: `ftp_perfect-jewel-active-sync/docs/DATABASE-GUIDE.md`.
  - Links from `README.md` and `DATABASE.md`. Interactive canvas beside chat for the same ERDs / page picker.
- **Follow-ups / open:**
  - In-app `/dev/db-workbench/` and `/dev/data-map/` remain the live browsers; this guide is the reading version.
  - Gold batch / invoice-create approval still iadmin-only (called out in the guide).
- **Commits (if any):** none yet

### 2026-09-11 — Consignment due alarm (warn only)

- **Source:** Cursor chat “can the alarm act like a notification window… Carry product_type + purchase_date + due_date onto ProductMaster”
- **Goal:** Copy iadmin supplier-consignment dates onto Django, then remind (sound + window + header bell) for overdue / due within 7 days — same shape as reserve alerts, without auto-returning stock.
- **Done:**
  - `ProductMaster` now has `product_type`, `purchase_date`, `due_date` (`DateField`) plus migration `0007`. Sync parses DD-MM-YYYY, Excel serials, and “consignment” vs “Purchased”.
  - Home KPI + table, header bell (replaces fake INV/TR rows), and a reminder modal with a two-tone chime. Dismiss today / mute / session snooze. Nothing writes stock or payments.
  - Product list filters: purchase type + due (open / overdue / today / soon). Spec sheet shows the dates.
  - Tests cover date parse, summary counts, home/bell HTML, and product detail.
- **Follow-ups / open:**
  - Same alarm is now on local iadmin (`ftp_perfect-jewel-active-sync`) — popup + Consign header count + rebuilt `consignment_alert_master.aspx` (chips, SQL filters). Dashboard company stock no longer includes reserved pieces; unpaid is pesos. Not on live FTP until those files are uploaded.
  - Re-run `sync_legacy_mssql` / snapshot import so the ~4,100 live consignment lots get dates. Until then the Django alarm only sees demo `ZZ-ALARM-*` rows (and any later sync).
  - After that re-sync the Django bell badge will be large (thousands overdue in the dump as of 11 Sep 2026) — summary counts are intentional.
  - Browsers often block the chime until the first click.
- **Commits (if any):** none yet

### 2026-09-09 — Live data health on the developer pages

- **Source:** this chat — owner brief was a frozen printout; asked for actual health that checks the data
- **Goal:** A developer-only page that queries live iadmin read-only and reports what is wrong now.
- **Done:**
  - `/dev/health/` behind `developer_required`. SELECT only. Re-runs on refresh.
  - Checks: server clock vs Manila, live/cancelled invoice totals and date window, complete uninvoiced assignments with soldqty 0, unpaid last-balance vs billed-less-payments, sold_status vs item_current_status, empty purchase_price, consignment share of unsold pieces, transfers still pending.
  - Owner brief stays the frozen August printout and links here.
- **Follow-ups / open:**
  - Page only shows live numbers when this Django process can reach mssql.tag11.in. A failed connection is shown, not guessed.

### 2026-09-09 — Owner brief on the developer pages

- **Source:** this chat — financial-health read of the iadmin restore, then “add this to the dev view”
- **Goal:** A developer-only page Jeff can open and present: health numbers and confirmed bugs, not the rate-ask.
- **Done:**
  - New `/dev/owner-brief/` behind `developer_required`. Nav item **Owner brief**, linked from Data map, DB workbench, and DB sync. Print button.
  - Figures are the 13 Aug restore queried 9 Sep: net invoiced ₱9,090,832, 87% of vault consignment, ₱3.0M outstanding, assignment 97 at ₱7,547,626, unpaid 35 vs 54, wrong clock, Indian peso grouping, 291 “active” transfers.
  - Says what the system cannot answer (no 12-month history, no cost/margin) and what is already fixed in code versus not yet FTP’d.
  - Compensation / day-rate material is deliberately not on the page.
  - `OwnerBriefTests`: developer sees the figures; ordinary staff get 403.
- **Follow-ups / open:**
  - Re-pull production and refresh the brief once mid-Aug through September is in the restore. These numbers stop at 12 Aug.
  - iadmin dashboard fixes still need a human FTP upload before they are live.

### 2026-09-09 — Stop the mirror drifting; honest dashboard wording; owner one-pager

- **Source:** this chat — live tile-by-tile comparison of `perfect-jewel.svojas.co/iadmin/` against `pjsystems.itsshin.dev`
- **Goal:** Find out why the two dashboards disagree, fix the cause rather than the display, and leave the owner something readable.
- **Done:**
  - **Found the drift.** iadmin: 577 sold / 7,387 company stock. Here: 337 / 7,626. `_import_items` skipped `status` and `location` on update by design, so a piece imported as company stock stayed company stock forever. New pieces arrived (both systems agree on 7,964 total); nothing that *changed* about an existing piece did.
  - **Found a second location bug.** Item location was read from `tblproduct_master.company_locationid` — the shared *design* row — so 6,646 pieces sat at HO here while iadmin had Main Vault 5,624 / Pullout 1,166 / Show Room 201. Now follows `InventoryLocationHelper` precedence: per-barcode `tblproduct_detail_master.company_locationid`, then master, then HO.
  - Re-sync now refreshes `ProductItem.status`/`location`/`reprint_status` and `AssignmentMaster.invoice_status`. `--preserve-local-state` restores the old behaviour for the day Perfect Jewel actually works in this system.
  - **Imported two tables that were being skipped entirely.** `tblproduct_transfer` (as history — mapped to `COMPLETE`, because `return_status` defaults to `'pending'` and iadmin never moves it, which is why the legacy dashboard advertises 291 active transfers with nothing in transit) and `tblproduct_tracker` (dated by `scan_date`, so "scans today" means today). Added `legacy_id` to `Transfer` and `TrackerSession`, plus `ScanMode.TRANSFER` for legacy `workflow_mode='transfer_only'` sessions.
  - **Dashboard wording follows the data:** peso figures beside stock counts labelled *at list price* (they are sums of catalogue `selling_price`); the Assigned tile no longer claims "None currently out" at zero and points at By location; new `core.SyncRun` row per run puts "as of when" on the page, replacing a cache key that did not survive a Render restart.
  - `apps/core/tests.py` now covers the drift itself (15 tests); `config/settings_sqlite.py` runs the suite without a local Postgres. Full suite 22 passing.
  - `OWNER-ONE-PAGER.md` — plain-language status of both systems for Perfect Jewel.
- **Sync run 2026-09-09 03:25 (Render, `prod` / `pj_erp_db`), results:**
  - Sold **337 → 577** (exact match with iadmin). Company stock **7,626 → 7,386** vs iadmin 7,387.
  - Locations now real: HO 6,646 → **Main Vault 5,625, Pullout 1,166, Admin Room 406, Show Room 201, Amara Shia 160, Hanz 99, Dani 67**, 49 stocked in total.
  - Invoice status refresh moved 4 masters that had been frozen since first import: complete **189 → 186**, cancelled **43 → 47**, unpaid **78 → 75**, invoiced **₱25,583,563 → ₱25,543,452**.
  - Tracker history imported (SN533–SN538 visible, incl. the 2,600-piece Show Room closing scans). Transfers pending **0** — the `return_status='pending'` mapping held.
- **Follow-ups / open:**
  - Off by one against iadmin (company 7,386 vs 7,387, Main Vault 5,625 vs 5,624). MSSQL has 7,965 detail rows to our 7,964 — one is unimportable — but the Main Vault delta points the other way, so ~2 pieces are placed differently. Not chased.
  - **iadmin's "today" is the SQL server's day, not Manila's.** `adminhome.aspx.cs:98` uses `CAST(GETDATE() AS DATE)`; at 02:28 PHT on 9 Sep it still counted 8 Sep scans as "today". Django (`Asia/Manila`) correctly said no scans yet. Real defect on the legacy side.
  - Django lists each reseller location code separately (Donnalyn Bartolome appears as 46 + 25 + 16 + …); iadmin groups her 6 codes into one bar of 99. Presentational difference, no grouping model here.
  - `/dev/db-sync/`'s "Last sync log" reads an in-memory cache, which is per gunicorn worker and empty after a restart — it showed "Sync running…" and "no run recorded" while the run had in fact finished. Should read `core.SyncRun` instead.
  - Direct MSSQL from the laptop still fails (DNS); live checking was done by logged-in HTML scrape. Local Postgres service reports Running but listens on nothing.
  - iadmin's own dashboard still shows the "Assigned 0" and "291 active transfers" traps to the owner. Same wording fix would apply there.
  - Retire the `1001` / `changeme123` login before showing the site around.
- **Commits (if any):** `31f2fb9` — Let a re-sync from iadmin correct stock state, not just add new pieces

### 2026-09-09 — Docs review vs iadmin sibling; work-log convention in both repos

- **Source:** Cursor chat “check the docs” on `ftp_perfect-jewel-active-sync` and this repo
- **Goal:** Read both documentation trees; give the FTP repo the same living `PROJECT_WORKLOG.md` this file already is.
- **Done:**
  - Confirmed this file is the current Django picture; `README.md` lags (hardware + staff UI exist; sync/hr/reporting still stubs).
  - FTP sibling now has `PROJECT_WORKLOG.md` (created from its git history). Spec docs there remain `CLAUDE.md` / `SYSTEM-AUDIT.md` / scan + inventory + hardware.
  - Broken in-repo pointers here: `IADMIN-SYSTEM-REFERENCE.md`, `django-rebuild-plan.md`, `REBUILD-ARCHITECTURE-AND-BUDGET.md` (ShinTools) are cited but not in this repo.
- **Follow-ups / open:**
  - Refresh `README.md` to match this work log (hardware/Irys/UI built; remaining gaps listed honestly).
  - Optional: vendor or link the missing architecture/reference markdown so model docstrings stop pointing at ghosts.
- **Commits (if any):** none yet for this slice.

### 2026-09-08 — Create the developer login when the web app boots

- **Source:** this chat; production sign-in still rejected `dev` after deploy `758bbf6`
- **Goal:** Sign in on the live site as `dev` even if Render starts gunicorn without `scripts/start.sh`.
- **Done:**
  - `config/wsgi.py` creates or updates the developer login from `DEV_ACCOUNT_PASSWORD` after Django starts. The password is not passed on the shell and is not written to the log.
- **Follow-ups / open:**
  - Sign in on `pjsystems.itsshin.dev` with employee code `dev` only after this commit is Live. Password is the value already set on the Render service.
- **Commits (if any):** this commit — create the developer login when the web app boots.

### 2026-09-08 — Persist jefffffff label layout on live

- **Source:** this chat; local designer `/hardware/templates/1/`
- **Goal:** Keep the `jefffffff` Irys layout after deploy, on live Postgres as well as this machine.
- **Done:**
  - Layout is in `apps/hardware/saved_layouts.py` (colour at 783,47; offsets −35 / 55; ANY default).
  - `ensure_label_templates` restores that named row only. It does not wipe other templates.
  - Render `start.sh` runs that command after migrate. Migration `0011` upserts the same spec once.
- **Follow-ups / open:**
  - Designer edits to `jefffffff` need a dump back into `saved_layouts.py` or the next boot restores this snapshot.
- **Commits (if any):** `79ca85e` — Persist the jefffffff label layout across deploys.

### 2026-09-08 — Developer login for /dev/ pages

- **Source:** this chat
- **Goal:** One developer account that can see every page plus the database tools, on the deployed site as well as locally.
- **Done:**
  - `Employee.is_developer`. `/dev/` pages and print-sheet sync return 403 for anyone else. Sidebar links appear only for that login.
  - `manage.py ensure_developer` creates employee_code `dev`. Created on this machine’s `pj_erp_prod` only.
- **Follow-ups / open:**
  - After this code is on Render, run `ensure_developer` once against the live database. The local password does not exist there yet.
- **Commits (if any):** none yet.

### 2026-09-08 — DATAFILE print sheet sync

- **Source:** this chat; public copy of the Tiara sheet
- **Goal:** Fill karat and net weight from DATAFILE, matched on RFID Tag, without treating a blank metal type as Silver.
- **Done:**
  - Sync print sheet on `/products/add/` updates existing pieces only. PJ25073 is now Gold / `18K+3G` / 9.05 g.
  - Local run: 7874 matched, 7470 updated, 1367 sheet rows not in this catalog.
- **Follow-ups / open:**
  - This wrote the local catalog only. Production still needs this after they ask to push.
- **Commits (if any):** none yet.

### 2026-09-08 — Default label preview zoom 1×

- **Source:** this chat
- **Goal:** Open `/hardware/templates/1/` at 1× preview zoom, matching print.
- **Done:**
  - Designer config and fallback zoom start at 1× (`1.0×` label).
  - Print preview cards also open at 1×; Fit still scales to width.
- **Follow-ups / open:**
  - Staff can still zoom in with + / Fit.
- **Commits (if any):** none yet.

### 2026-09-08 — Add stock by jewellery Excel

- **Source:** this chat; `YZC 9-8-26.xlsx` is the Product Master upload
- **Goal:** Add pieces in Django the same way staff add them on iadmin — Excel first, one-piece form second.
- **Done:**
  - `/catalogue/add/` reads the Jewellery Excel sheet (header on row 2). Match is the PJ code: new row creates a design plus a piece; a known PJ is updated.
  - `DFLT - 18K` is stored as purity `18K` and metal Gold. A blank metal name is not saved as Silver.
- **Follow-ups / open:**
  - This writes the Django catalog only. It does not push back to live iadmin.
- **Commits (if any):** none yet.

### 2026-09-08 — YZC intake sheet vs what the upload stored

- **Source:** `Downloads\YZC 9-8-26.xlsx`; Product Master “Upload Excel” opens `website_product_reference.aspx`
- **Goal:** See what Cylver’s jewellery upload actually wrote on live iadmin.
- **Done:**
  - Sheet is 226 consignment pieces, owner YZC1, PJ24881–PJ25106. Metal name blank. Purity text is `DFLT - 18K` (203), plus PT900 / PT850 / PT950. Markup 10.
  - All 226 barcodes are on live `stock_rfid`. Weights match. `metal_id` is 1 (Silver) and `metal_purity_id` is empty on every row — the `DFLT - 18K` text did not land as a purity id.
- **Follow-ups / open:**
  - Do not treat stock-report karat or `metal_id` 1 as the label. Print source is still DATAFILE. This sheet is the intake file.
- **Commits (if any):** none.

### 2026-09-08 — Read-only DB workbench for live schema

- **Source:** this chat; user asked for the iadmin workbench layout, for every database, with clearer relationships
- **Goal:** Show the actual tables, columns, and joins for live iadmin and the Django catalog — read only, no sidebar link.
- **Done:**
  - `/dev/db-workbench/` lists live `stock_rfid` (79 tables, 0 foreign keys, 17 known joins) and the active Postgres catalog (real foreign keys).
  - Click a table for columns, key, and what it points at / what points at it. Overlapping metal ids are marked, not treated as names.
- **Follow-ups / open:**
  - Still local-only until they ask to push. DATAFILE purity is still not imported.
- **Commits (if any):** none yet.

### 2026-09-08 — Stock-report karat is purity + country suffix

- **Source:** this chat; stock new report for `PJ23380` shows `18K-Japan Gold`
- **Goal:** Match the stock-report purity label, keep the origin suffix, and clarify sync vs the other legacy reports.
- **Done:**
  - `metal_purity_id` on metal details is `tblpurity_country_mgmt` (18K + Japan Gold), not `tblMetalpurity_master` (which made the same id look like 24K / Silver).
  - Label is `18K-Japan Gold`. A DEFAULT/DFLT country drops the suffix so it stays `18K`, not `DFLT - 18K`.
- **Follow-ups / open:**
  - Live weight numbers were written on the earlier MSSQL sync; the piece page shows them after the display deploy. Corrected karat needs this commit on Render, then another live sync. Do not sync before that deploy or the old mapping can write the wrong karat.
- **Commits (if any):** this change.

### 2026-09-08 — Piece weight and karat from jewellery metal details

- **Source:** this chat; live piece page for `PJ23380`
- **Goal:** Show weight and 18K/purity that iadmin reports read from metal-detail rows, and strip a leading `DFLT -` purity prefix.
- **Done:**
  - Confirmed `tblproduct_master.net_wt` / `metal` are usually empty; stock reports use `tbljewellery_metal_details.weight` plus `metal_id` (`tblmetalcountry_master`) and `metal_purity_id`.
  - Piece/design pages fall back to that weight. Import now fills net weight, metal, and purity from those rows. `DFLT - ` is stripped on import and display; the rest of the label is kept (no extra toggle).
- **Follow-ups / open:**
  - After this lands on Render, re-run the live MSSQL sync so metal/karat columns fill on `pjsystems.itsshin.dev`. Weight can show from existing `gold_weight` as soon as the template deploys.
- **Commits (if any):** this change.

### 2026-09-08 — Ship local catalogue, media, and DB Sync

- **Source:** this chat; git after `6332eeb`
- **Goal:** Commit and push the unpublished local work already logged below (nothing was left unpushed on `main`).
- **Done:**
  - Pushed products list UX, dashboard tag sequences, search tweaks, R2 storage settings + `upload_local_media`, DB Sync page (`/dev/db-sync/`), brand icons used by the shell/login.
- **Follow-ups / open:**
  - Confirm Render `AWS_*` and redeploy.
  - Do not add a sidebar DB Sync link until you want it visible; the URL works without it.
  - Left untracked: `.cursor/`, and ~352 MB of extra login JPGs (not the `pj-01.jpg`… set already referenced).
- **Commits (if any):** this push.

### 2026-09-03 → 2026-09-07 — Live MSSQL sync + DB Sync status page

- **Source:** Cursor chat [Live MSSQL sync and DB status](97ec69f1-b5f2-430a-83f9-f70dc9f8b38f) (started 2026-09-03; wrap-up logged 2026-09-07)
- **Goal:** Put live iadmin `stock_rfid` data into the Django Postgres catalogs; add a simple dev page showing whether MSSQL vs `pj_erp_prod` / `pj_erp_dev` are in sync; clarify whether the Django schema is clearer to navigate than legacy.
- **Done:**
  - Ran `sync_legacy_mssql` into active profile **prod** (`pj_erp_prod`), then `clone_prod_to_dev --yes` so both catalogs match. Credentials were already in gitignored `.env` (`LEGACY_MSSQL_*`).
  - First sync (2026-09-03): ~7,428 products/items, 111 resellers, 219 invoices, 149 reseller payments (deltas vs prior dump: +40 products/items, +2 resellers, +21 invoices, +19 payments).
  - Second sync (same chat, later): ~7,429 products, 7,429 items (1 MSSQL row skipped), 220 invoices, 1,353 lines, 149 payments; then re-cloned to `pj_erp_dev`.
  - **DB Sync status page (local / uncommitted):** `/dev/db-sync/` — COUNT(*) compare of live MSSQL vs both Postgres catalogs; overall synced with soft rules (items may be −1; locations/categories may be ahead locally); connection panels; last sync log from cache; **Sync now** POST (background thread, same lock as webhook). Helpers: `apps/core/sync_status.py`, `count_live_tables` / `ping_live` in `legacy_mssql.py`, views `db_sync_status` / `db_sync_run`, template `templates/core/db_sync_status.html`.
  - Sidebar **DB Sync** nav was added in-session but is **not** on current `templates/base.html` (matches `main` after the Sep 4 accidental-nav 500 fix). Route still works if you hit the URL while local code is loaded.
  - Schema Q&A (no code): Django is the clearer map for “where data lives” (real FKs/indexes, typed fields, location on `ProductItem`, `StockStatus` choices, audit timestamps); legacy remains the live ops source during transition, with placeholders/SPs/no FKs making navigation hard.
- **Follow-ups / open:**
  - Commit + deploy DB Sync page **with** urls/views/template together; only re-add the sidebar link when brand static + this route ship in the same deploy (see `0112cfb`).
  - After future prod syncs, run `clone_prod_to_dev --yes` if the working copy should match.
  - Re-sync still useful so Irys gold/diamond weights from legacy metal/stone detail tables fill after `cdafad0`.
- **Commits (if any):** none yet — sync was operational (data only); DB Sync UI remains working-tree / untracked (`sync_status.py`, `db_sync_status.html`; modified `views.py` / `urls.py` / `legacy_mssql.py`).

### 2026-09-07 — Products identity UX + dashboard tag sequences

- **Source:** Cursor chat [View by PJ codes](1865161a-2a3c-41d7-999a-0f23f2c04dc8)
- **Goal:** Decide whether `/products/` should “view by PJ code / barcode”; fix the wall of repeated style names (e.g. ANICH1); surface latest PJ / PJGOLD so new tags don’t collide.
- **Done (local / uncommitted):**
  - Confirmed piece view already exists at `/products/item/<barcode>/`; nav search exact-match already redirects there. No separate “by PJ” filter chip needed.
  - **Products list identity:** lead with **Reference** (unique), demote shared **Style** name; add **PJ / barcode** column (link to piece when `item_count == 1`); grid cards use `pl-card-ref` + sample barcode annotation; default sort **Reference A–Z**; exact PJ/barcode/EPC on list `q` redirects via `_exact_item`.
  - Product detail title and global search product results/suggest also lead with `reference_id`.
  - **Dashboard Tag sequences:** highest numeric `PJ#####` and `PJGOLD####` (not lex sort), suggested next codes, plus piece details (reference, style, status, location, category/supplier, recorded). Display-only — no DB reservation. `_latest_barcode_series` in `apps/core/views.py`; UI in `templates/core/home.html` + `.dash-seq-*` CSS.
- **Follow-ups / open:**
  - Commit + deploy with other local catalogue/media work; hard-refresh / collectstatic so CSS lands on Render.
  - Optional later: copy-to-clipboard on suggested next; same hint in admin item create; exact `reference_id` redirect; group-by-style toggle.
- **Commits (if any):** none yet for this slice (working tree). Related prior list rewrite: see entry below from [UI and UX enhancement](0482c868-02fa-40dd-98b5-add162273e99).

### 2026-09-04 → 2026-09-07 — Production media via Cloudflare R2

- **Source:** Cursor chat [Production image display issue](90742bd3-47e2-44c2-8878-d84a7f0b37d5) (started 2026-09-04; wrap-up logged 2026-09-07)
- **Goal:** Fix product / upload pictures missing on Render production.
- **Done (local / uncommitted code + ops):**
  - Root cause: `media/` is gitignored + ephemeral on Render; Django only served media when `DEBUG=True`; WhiteNoise does not serve uploads; brand files under `static/core/img/brand/` were never committed.
  - Added S3-compatible default storage (`django-storages` + `boto3`) when `AWS_STORAGE_BUCKET_NAME` is set; local `FileSystemStorage` otherwise. Absolute `/static/` and `/media/` URLs.
  - Production media serve via `django.views.static.serve` when not on S3 (`SERVE_MEDIA`; `static()` is a no-op with `DEBUG=False`).
  - `upload_local_media` management command (exact-key PutObject — avoids django-storages rename suffixes that would break DB paths).
  - Invoice PDF logo uses WeasyPrint-safe URI (`file://` locally / HTTPS on R2) instead of `.path`.
  - Documented R2 env vars in `.env.example` + README media section.
  - Ops: created public R2 bucket `pj-erp-media` (`pub-….r2.dev`); uploaded **833** local media keys with `--force`. Guided Render env (endpoint needs `https://`; custom domain is host-only, no dashboard URL).
- **Follow-ups / open:**
  - **Commit + push** this media stack (and ideally `static/core/img/brand/`) — not on `main` yet; Render will not pick it up until then.
  - Confirm all seven `AWS_*` vars are present on Render (`BUCKET`, keys, `ENDPOINT_URL` with `https://`, `REGION=auto`, `CUSTOM_DOMAIN=pub-….r2.dev`, `QUERYSTRING_AUTH=False`), then rebuild/deploy.
  - Rotate R2 API token if secrets were exposed in screenshots/chat.
  - After deploy, verify a product thumb hits `https://pub-….r2.dev/product_images/…`.
- **Commits (if any):** none yet for this slice (working tree + untracked `upload_local_media.py`).

### 2026-08-26 → 2026-09-07 — Dashboard vs snapshot, search overlay, status audit

- **Source:** Cursor chat [Dashboard and status audit](fbf2fc72-ab0b-4c40-aad1-c3681d595354) (started 2026-08-26; wrap-up logged 2026-09-07). Git not readable in this workspace this turn (no `.git`); related dashboard/search work on `main` is already in the Aug 27 / Sep 4 appendix rows.
- **Goal:** After the FTP MSSQL snapshot was in Postgres, tailor the home dashboard to real counts; fix the broken search dropdown; answer how to switch catalogs and whether prod has the dump; then a no-code project-status audit before the next build phase.
- **Done:**
  - Dashboard shaped around this catalog (company stock + invoice history, not empty “holding now”): sales band (invoiced / collected / collected this month / unpaid outstanding), sold KPI link, subcategory labels (ER → Earrings, …), empty locations hidden until toggled, top resellers by invoiced value, recent invoices with peso amounts. Assigned = 0 is real for this dump.
  - Search suggestions dropdown was transparent (`background: var(--panel)` with `--panel` undefined). Defined `--panel` as the opaque surface color; moved `.search-dd` into `base.css`.
  - Switch catalogs in gitignored `.env` (`DJANGO_DB_PROFILE=dev|prod`), then restart `runserver` — not `.gitignore`. Removed a stray `DJANGO_DB_PROFILE=dev` line that had been pasted into `.gitignore`.
  - Dump vs `pj_erp_prod`: all chosen operational tables matched (6,656 items, 60 resellers, 135 invoices, 81 reseller payments). Not a live `tag11.in` pull; employees/tracker/transfers left out on purpose.
  - 2026-09-02 **audit only** (no code changes): operator payments UI, transfers UI, view-level authz, tests, and deploy hygiene are the main remaining gaps. Invoice PDF on this Windows box needs GTK/Pango for WeasyPrint. Estimate ~38% overall / ~8% production-ready.
- **Follow-ups / open:**
  - Next build priorities from the audit: payments on the invoice screen, transfers staff UI, real authorization, rotate `1001`/`changeme123`, tests on assign/return/status.
  - Do not start reporting UI or Tiara push until those backends exist; don’t run `sync_legacy_mssql` against the frozen `prod` profile if that catalog must stay a dump snapshot.
- **Commits (if any):** none from this wrap-up. Early-thread UI likely already on `main` (see Aug 27 dashboard/search commits and Sep 4 search UX). Appendix not refreshed (git unavailable here).
- **Note (2026-09-07):** Local `pj_erp_prod` was later **intentionally** refreshed from live `stock_rfid` via `sync_legacy_mssql` + `clone_prod_to_dev` (see entry *Live MSSQL sync + DB Sync status page*). Treat “frozen dump” as policy only when you need a stable snapshot again — not current local state.

### 2026-09-07 — Products catalogue list UI/UX

- **Source:** Cursor chat [UI and UX enhancement](0482c868-02fa-40dd-98b5-add162273e99) (started 2026-09-03; wrap-up logged 2026-09-07)
- **Goal:** Enhance `/products/` UI/UX so the jewellery catalogue is browsable visually and filters stay usable at ~7k designs.
- **Done (local / uncommitted):**
  - Default **grid** of product cards (image, stock pill, reference, category, metal, price) plus **list** table toggle; 24/page grid, 50/page list.
  - Summary strip: designs / with available / none available / no pieces / free-piece rollup; stock chips preserve other filters.
  - Filter bar with icon search, selects auto-submit on change, removable filter chips, clearer empty state.
  - Pagination preserves all query params (incl. subcategory + view); page-number window with ellipsis.
  - Exact PJ/barcode (or RFID EPC via `_exact_item`) on list search redirects to the piece page; default sort is **reference_id** (style names often repeat, e.g. ANICH1).
  - `OUT` stock filter = pieces exist but none available (no longer lumps in zero-piece designs).
  - Styles: `.pl-*` block in `static/core/css/base.css`; template `templates/catalogue/product_list.html`; logic `apps/catalogue/views.py`.
- **Note (2026-09-07):** Reference-first columns, sample barcode on cards/list, and search suggest leading with `reference_id` were finished / tightened in [View by PJ codes](1865161a-2a3c-41d7-999a-0f23f2c04dc8) (entry above) on the same uncommitted tree.
- **Follow-ups / open:**
  - Commit + deploy this products list work (still local alongside other unpublished changes — brand assets, DB Sync page, etc.).
  - Hard-refresh / collectstatic on Render after ship so `.pl-*` CSS is live.
- **Commits:** none yet for this slice.

### 2026-09-07 — Irys stone weights + print history

- **Source:** Cursor chat [RFID template creation](7595b338-6c4e-4d0d-8447-abaee22ff223); git `cdafad0`, `ded183e`
- **Goal:** Finish Irys tag accuracy (registration, stone line) and add an audit trail of prints.
- **Done:**
  - ProductMaster tag attrs: `colour`, `size`, `quality`, `stone`, `gold_weight`, `diamond_weight` (+ migration `catalogue.0006`).
  - Legacy import pulls gold from `tbljewellery_metal_details`, diamond from `tbljewellery_stone_details` (ND/LGD/LABGROWN subcats); stone field prints `D-…` and/or `G-…` (only what exists; left-aligned as one string).
  - Irys Offset X default **−35**, Offset Y **55** @ 300 DPI; sample layout reapplied (`hardware.0009`) with stone on front face.
  - **Label print history:** `LabelPrintLog` (`hardware.0010`); log on BrowserPrint send success/fail; `/hardware/print/history/`; times-printed on preview cards.
- **Follow-ups / open:**
  - Re-run `sync_legacy_mssql` (or usual sync) on prod so weights fill.
  - Nudge Offset X further in designer if physical stock still drifts.
  - Print log is best-effort client-reported (Zebra BrowserPrint), not printer confirmation.
- **Commits:**
  - `cdafad0` — Import real gold/diamond tag weights and print D-/G- on Irys labels.
  - `ded183e` — Add label print history for Zebra BrowserPrint jobs.

### 2026-09-04 — Global search coverage & UX

- **Source:** Cursor chat [Search coverage and UX](bc78b905-8f7b-4539-b0e6-4334f0af278e); git `73d0240`, `0112cfb`
- **Goal:** Confirm whether nav/`/search/` covered “everything,” expand the high-value gaps, and polish dropdown + results + mobile UX (scope **1A + 2C**).
- **Done:**
  - Coverage: invoices (`RE…`/`RN…` + reseller name), RFID EPC (partial + exact→item), products also match via piece barcode (aligned with product list).
  - Still out of global search (little/no detail UI): payments, transfers, returns, hardware templates.
  - UX: mobile search overlay (was `display:none` under 900px); dropdown loading / match highlight / group counts / kbd hints; results page jump chips, hint cards, clearer empty state.
  - Files: `apps/core/search.py`, `templates/core/search.html`, `static/core/js/search.js`, `templates/base.html`, search styles in `static/core/css/base.css`.
  - Prod incident: deploy of `73d0240` 500’d every authenticated page — `base.html` had accidentally shipped local-only **DB Sync** `{% url %}` (route not on `main`) + missing brand static; login + `/search/suggest/` still worked (no shell template). Fixed in `0112cfb`.
- **Follow-ups / open:**
  - Brand images + DB Sync page remain local/untracked — don’t link them from templates until committed with assets + urls/views.
  - Optional later: Postgres FTS/trigram when item table grows (noted in `search.py`).
- **Commits:**
  - `73d0240` — Expand global search coverage and polish search UX.
  - `0112cfb` — Fix production 500 from accidental base.html nav changes.

### 2026-09-03 → 2026-09-04 — Irys RFID designer & print accuracy

- **Source:** git `5ed692d` … `a2aa023` (and related); Cursor RFID sessions
- **Goal:** Rebuild jewellery RFID printing around **Irys Standard** die-cut (25×13 mm faces + 50 mm tail → ~75×26 mm @ **300 DPI** ≈ 886×308 dots).
- **Done (high level):**
  - Media profiles, designer zones (tail / front / back), sample layout as single source of truth.
  - Fixed ZPL escaping (`json_script` vs broken `|escapejs`); no `^LL` on continuous Irys stock.
  - DPI migrate 203→300 so faces weren’t crushed into one panel.
  - Die-cut registration: Offset Y ~55; Offset X nudged left (−18 then later −35).
  - Preview = design coords on-tag; offsets only in ZPL for printer registration.
  - Tag prices as whole numbers; stone formatting helpers G-/D- (real weights wired 2026-09-07).
  - *(Search coverage/UX + prod 500 fix from the same calendar day are detailed in the **2026-09-04 — Global search** entry above, not re-listed here.)*
- **Commits (selected):** `5ed692d`, `f242bbd`, `b1d7618`, `7a730ec`, `e544898`, `cc71518`, `f8756e3`, `cd26da8`, `3b63707`, `a2aa023`.

### 2026-08-28 — Deploy, legacy sync, product images, login

- **Source:** git `e0ed430` … `950fe97`
- **Done:**
  - Gunicorn + WhiteNoise for Render.
  - `legacy_id` + live MSSQL `sync_legacy_mssql`; cron-job.org webhook (fire-and-forget for 30s timeout).
  - Invoice print stylesheet / PDF link; rebuilt sign-in; product images; login split closer to iadmin.
- **Commits:** `e0ed430`, `74efdcf`, `f270b40`, `1a2955f`, `22927cd`, `c760843`, `6bd3f76`, `950fe97`.

### 2026-08-27 — App shell & first feature UIs

- **Source:** git `337a830` … `626da08`
- **Done:**
  - Sidebar / topbar / theme / DB badge shell.
  - Stock by location; product tracker scan flows; **Zebra tag printing + label designer** (first pass).
  - Product master list/detail; reseller groups & invoices; invoice cancel return-status fix.
  - Global search; dashboard money figures; invoice PDF; returns app; legacy document import.
  - `DATABASE.md` and wiring notes.
- **Commits:** `337a830`, `56885cc`, `e600e22`, `a79f0bd`, `a0d00fa`, `732c490`, `1457270`, `c0150f0`, `ed869fc`, `626da08`.

### 2026-08-19 — Scaffold & parity pass 2

- **Source:** git `0dbcae1`, `b3695aa`
- **Done:**
  - Django + Postgres scaffold: core, accounts, locations, catalogue, inventory, tracker, transfers.
  - Transfers, assignment/invoicing, returns/reserves, payments — fuller parity pass.
- **Commits:** `0dbcae1`, `b3695aa`.

---

## Commit appendix (chronological, from git)

Generated from `main` as of **2026-09-07**. Newest work is also summarized above.

| Date | Hash | Message |
|------|------|---------|
| 2026-08-19 | `0dbcae1` | Scaffold Django+Postgres rebuild: core/accounts/locations/catalogue/inventory/tracker/transfers |
| 2026-08-19 | `b3695aa` | Build transfers, assignment/invoicing, returns/reserves, payments — full parity pass 2 |
| 2026-08-27 | `7fbc133` | Ignore raw legacy SQL import dumps |
| 2026-08-27 | `337a830` | Add application shell: sidebar, topbar, theme toggle, DB profile badge |
| 2026-08-27 | `56885cc` | Add stock-by-location list and per-location item detail |
| 2026-08-27 | `e600e22` | Add product tracker scan flows; classify opening scans by real item status |
| 2026-08-27 | `a79f0bd` | Add Zebra tag printing with visual label designer and ZPL generation |
| 2026-08-27 | `a0d00fa` | Add product master: design list, design detail, single-item page |
| 2026-08-27 | `732c490` | Add reseller groups, client directory, and invoice create/stamp screens |
| 2026-08-27 | `1457270` | Return ASSIGNED and RESERVED items on invoice cancellation, not only SOLD |
| 2026-08-27 | `c0150f0` | Add global search; make dashboard money figures discount-aware |
| 2026-08-27 | `ed869fc` | Add database notes and remaining wiring |
| 2026-08-27 | `626da08` | Add invoice PDF generation, returns app, legacy document import, global search, and dashboard money-figure fixes |
| 2026-08-28 | `e0ed430` | Add gunicorn and whitenoise for production deployment (Render) |
| 2026-08-28 | `74efdcf` | Remove hardcoded admin credential hint from login page |
| 2026-08-28 | `f270b40` | Add legacy_id tracking + live MSSQL sync (sync_legacy_mssql) for safe, recurring iadmin imports |
| 2026-08-28 | `1a2955f` | Add free cron-job.org-triggered webhook for sync_legacy_mssql (no paid Render Cron Job needed) |
| 2026-08-28 | `22927cd` | Make sync_legacy_webhook fire-and-forget so cron-job.org's 30s timeout doesn't matter |
| 2026-08-28 | `c760843` | Add print stylesheet and PDF link to the invoice page |
| 2026-08-28 | `6bd3f76` | Rebuild the sign-in page: real form markup, password toggle, Caps Lock hint, DB badge |
| 2026-08-28 | `950fe97` | Add product images, and split sign-in to match iadmin |
| 2026-09-03 | `5ed692d` | Rebuild the RFID label designer around Irys jewellery-tag paper. |
| 2026-09-03 | `f242bbd` | Fix ZPL escaping that scrambled Irys RFID prints and improve print preview. |
| 2026-09-03 | `b1d7618` | Make the print-page label preview larger and easier to verify. |
| 2026-09-03 | `7a730ec` | Fix Irys RFID prints by switching templates to 300 DPI. |
| 2026-09-03 | `e544898` | Tighten Irys sample layout and print offset guidance. |
| 2026-09-03 | `cc71518` | Fix Irys die-cut registration on deploy via data migration. |
| 2026-09-03 | `f8756e3` | Make label preview die-cut accurate and migrate on every deploy. |
| 2026-09-03 | `cd26da8` | Make the Irys sample layout the single print-accurate source of truth. |
| 2026-09-03 | `3b63707` | Nudge Irys print left with Offset X −18 at 300 DPI. |
| 2026-09-04 | `73d0240` | Expand global search coverage and polish search UX. |
| 2026-09-04 | `0112cfb` | Fix production 500 from accidental base.html nav changes. |
| 2026-09-04 | `a2aa023` | Format tag prices as whole numbers and stone weights as G-/D-. |
| 2026-09-07 | `cdafad0` | Import real gold/diamond tag weights and print D-/G- on Irys labels. |
| 2026-09-07 | `ded183e` | Add label print history for Zebra BrowserPrint jobs. |
| 2026-09-07 | `a151c45` | Add PROJECT_WORKLOG.md as the living project work log. |

---

## Gaps this log cannot fully recover

- Work that never landed on `main` (local-only, discarded branches, or undocumented experiments).
- Verbal / offline decisions not in git or Cursor transcripts.
- Detailed day-by-day notes before 2026-09-07 sessions (reconstructed from commit messages only).

Other Cursor chats that may hold extra context to merge later: “Postgres database setup”, “Dual repository audit overview”, “Repo updates and documentation”, “Specific SN search for PJ codes”, [Search coverage and UX](bc78b905-8f7b-4539-b0e6-4334f0af278e), [UI and UX enhancement](0482c868-02fa-40dd-98b5-add162273e99) (products list), [View by PJ codes](1865161a-2a3c-41d7-999a-0f23f2c04dc8) (reference-first list + tag sequences).
