# Project work log — Perfect Jewel ERP (Django rebuild)

Living log of work on this repo (`pj_erp_django` / `pj-erp`).  
**There was no prior work log** — this file was created 2026-09-07 from git/`main` history plus Cursor session notes, so later sessions can **append** instead of rewriting.

| | |
|---|---|
| Repo | https://github.com/Shin-da/pj_erp_django |
| Branch | `main` |
| Deploy | Render (migrate + collectstatic on build; gunicorn) |
| Related docs | `README.md` (what’s built), `DATABASE.md` (DB notes) |

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

Catalogue UX, dashboard tag sequences, R2 media stack, DB Sync page, and brand icons are on `main` (see latest commit). Confirm Render `AWS_*` vars, then redeploy so product photos hit R2. DB Sync is at `/dev/db-sync/` — sidebar link still withheld so a missing route cannot 500 the shell (`0112cfb`). Ops gaps from the 2026-09-02 audit remain (payments UI, transfers UI, authz, tests).

---

## Snapshot (what this project is)

Full rewrite of Perfect Jewel’s daily RFID / iadmin-style ERP in **Django + PostgreSQL**, replacing ASP.NET Web Forms / SQL Server (`ftp_perfect-jewel-active-sync`). Decision recorded **2026-08-19**: parity rebuild with known legacy bugs fixed, not a greenfield redesign.

Major modules touched in commits so far: core, accounts, locations, catalogue, inventory, tracker, transfers, assignment/invoicing, payments, returns, hardware (Zebra / Irys tags), legacy MSSQL sync + cron webhook, product images, global search, Render deploy.

---

## Session / phase entries

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
