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

Irys Standard RFID jewellery tag printing: die-cut accuracy @ 300 DPI, real G-/D- weights from legacy sync, print history. Broader ERP parity (catalogue → inventory → tracker → assignment/invoices → payments/returns) is largely in place; hardware/Tiara sync, HR, reporting still lighter or pending per `README.md`.

---

## Snapshot (what this project is)

Full rewrite of Perfect Jewel’s daily RFID / iadmin-style ERP in **Django + PostgreSQL**, replacing ASP.NET Web Forms / SQL Server (`ftp_perfect-jewel-active-sync`). Decision recorded **2026-08-19**: parity rebuild with known legacy bugs fixed, not a greenfield redesign.

Major modules touched in commits so far: core, accounts, locations, catalogue, inventory, tracker, transfers, assignment/invoicing, payments, returns, hardware (Zebra / Irys tags), legacy MSSQL sync + cron webhook, product images, global search, Render deploy.

---

## Session / phase entries

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
  - Search UX polish; production 500 from accidental `base.html` nav fix (`0112cfb`).
- **Commits (selected):** `5ed692d`, `f242bbd`, `b1d7618`, `7a730ec`, `e544898`, `cc71518`, `f8756e3`, `cd26da8`, `3b63707`, `73d0240`, `0112cfb`, `a2aa023`.

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

---

## Gaps this log cannot fully recover

- Work that never landed on `main` (local-only, discarded branches, or undocumented experiments).
- Verbal / offline decisions not in git or Cursor transcripts.
- Detailed day-by-day notes before 2026-09-07 sessions (reconstructed from commit messages only).

Other Cursor chats that may hold extra context to merge later: “Postgres database setup”, “Dual repository audit overview”, “Repo updates and documentation”, “Specific SN search for PJ codes”.
