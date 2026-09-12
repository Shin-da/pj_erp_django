# Principal Engineer + Red-Team Full-System Audit

| | |
|---|---|
| **System** | Perfect Jewel ERP — Django rebuild (`pj-erp`) |
| **Tree audited** | `C:\Users\ONEGAI_SERVER\pj_erp_django\pj-erp` (working tree as of 2026-09-11) |
| **Runtime probe DB** | Local Postgres `pj_erp_prod` via `DJANGO_DB_PROFILE=prod` |
| **Standard** | Reality beats documentation. Evidence beats assumptions. |

This audit does **not** reassure. It records what was verified, what failed verification, and what remains unknown.

---

## Executive Summary

This system is a **partial operational ERP** with real catalogue/inventory/assignment/returns/tracker/hardware UI, a live MSSQL pull path, and a new DRF products API — running on Django 5.2 + PostgreSQL, deployed via Render (`Procfile` → `scripts/start.sh` → gunicorn).

It is **not** the parity rebuild the README still describes.

**Blunt assessment:**

1. **Authorization is login-only.** Any authenticated employee can create invoices, process returns, upload stock, mutate label templates, and use admin if they are staff. Django Groups/Permissions exist on the user model but are **not** enforced on views. The accounts module docstring claiming otherwise is false.
2. **Every legacy sync re-plants a known superuser password** (`1001` / `changeme123`) via `ensure_local_admin`. If the webhook runs against a real catalog, that is a standing credential reset, not a one-time bootstrap.
3. **Stock integrity is application-enforced only.** There is no DB `CHECK` on status, no `select_for_update` anywhere, and `ProductMaster.reference_id` is **not unique** — live data has **160 duplicate reference_id groups (359 rows)**. The API lookup-by-reference_id will raise `MultipleObjectsReturned` for those keys.
4. **Documentation is substantially stale.** README still says hardware/sync/hr/reporting are unbuilt; hardware is live. README FK/index counts are wrong. Payments/transfers are models+admin without staff UI. `django-q` is installed and configured but never run. Local `main` is **4 commits behind** `origin/main` while carrying a large uncommitted / untracked delta (including entire `apps/api/`).
5. **Tests do not prove the ERP.** `manage.py test` → **14 tests, all OK** — almost entirely catalogue/hardware. Core money/stock paths have stub test modules.

This is usable as a **developer-operated mirror + partial floor tool**. It is **not** safe to treat as a multi-role production ERP with trustworthy dual-write sync.

---

## System Reality

### What it actually is

```
Browser (staff) / cron-job.org / API clients
        │
        ▼
gunicorn (config.wsgi)  ← Procfile / scripts/start.sh
        │  migrate → ensure_label_templates → ensure_developer (if env)
        │  + wsgi-module boot: ensure_developer_account()
        ▼
Django middleware (Security, WhiteNoise, Session, CSRF, Auth, …)
        │
        ├─ Session login (Employee.employee_code) → @login_required views
        ├─ /dev/* → @developer_required (is_developer flag)
        ├─ /internal/sync-legacy-mssql/?token=… → shared secret (GET)
        └─ /api/v1/products/ → Authorization: Api-Key …
                │
                ▼
 Business logic in views + model methods
 (transition_status, invoice_create, returns.process, Transfer.execute, …)
                │
                ▼
 PostgreSQL (pj_erp_dev | pj_erp_prod by DJANGO_DB_PROFILE)
                │
                ├─ optional: pymssql SELECT from legacy MSSQL (sync)
                ├─ optional: Google Sheet CSV (Tiara DATAFILE)
                └─ optional: S3/R2 media (django-storages)
```

**No Redis. No running django-q worker. No CI in-repo. No Docker. No render.yaml in tree.**

### Apps (verified)

| App | Classification | Evidence |
|-----|----------------|----------|
| `core` | Active | URLs, sync webhook, search, home, schema browser |
| `accounts` | Active | Custom user, login, developer bootstrap |
| `locations` | Active (models) | Used everywhere; UI via inventory |
| `catalogue` | Active | Products, intake, photos, DATAFILE sync |
| `inventory` | Active | Items + location UI |
| `assignment` | Active | Resellers + invoices UI |
| `returns` | Active | Return scan UI |
| `tracker` | Active | Scan UI (+ experimental preview) |
| `hardware` | Active | Label designer + print — **README claims unbuilt** |
| `payments` | Partial | Models + admin + invoice payment display; **no staff payments UI** |
| `transfers` | Partial | Models + `execute`/`execute_return`; **0 Transfer rows locally; no UI; execute never called from views** |
| `api` | Active locally / untracked in git | DRF read-only products; mounted at `/api/v1/` |
| `sync` | Scaffold | `NOT YET BUILT` docstring; django-q unused |
| `hr` | Scaffold | `NOT YET BUILT` |
| `reporting` | Scaffold | `NOT YET BUILT` |

### Runtime verified (local)

| Probe | Result |
|-------|--------|
| Python | 3.12.10 via `venv` |
| Django | 5.2.17 |
| `manage.py check` | 0 issues |
| Migrations (local DB) | Applied through catalogue `0009`, accounts `0002`, api `0001`, … |
| `manage.py test` | **14 passed** |
| `DEBUG` | **True** (this machine’s `.env`) |
| `DJANGO_DB_PROFILE` | **prod** → `pj_erp_prod` |
| Row counts | ProductMaster 8882, ProductItem 8621, AssignmentMaster 254, ResellerPayment 199, Transfer **0**, ApiClient 1 (inactive) |
| FK count | **64** |
| Index count | **196** |
| ProductItem CHECK constraints | **0** |
| `ASSIGNED` items | **0** (206 COMPLETE invoices exist; lines point at SOLD/PENDING pieces — sync left status alone) |
| CACHES | Default **LocMemCache** |

---

## Critical Findings

### C1 — Sync re-creates known superuser `1001` / `changeme123`

| | |
|--|--|
| **Severity** | Critical |
| **Evidence** | `apps/core/legacy_import.py` end of `run()` calls `_ensure_login()` → `call_command("ensure_local_admin")`. Command hardcodes `LOCAL_PASSWORD = "changeme123"`, forces `is_staff`/`is_superuser`. Triggered by webhook `sync_legacy_webhook` and `/dev/db-sync/run/`. |
| **Impact** | Scheduled/manual sync **resets** a trivial admin password on the catalog being synced. Combined with flat authz, this is full system takeover. |
| **Verification** | Code path traced; command file read; call site confirmed. Not exercised live against production Render (no destructive prod action authorized). |
| **Recommendation** | Remove `_ensure_login` from sync entirely. Rotate any live `1001` credential. Bootstrap admin only via explicit one-shot ops command never wired to cron. |

### C2 — No real authorization beyond “logged in”

| | |
|--|--|
| **Severity** | Critical |
| **Evidence** | Grep: no `permission_required` / `user_passes_test` on business views. Smoke test: employee `1001` (non-developer) gets **200** on `/products/add/`, `/resellers/invoices/`, `/hardware/templates/`; **403** only on `/dev/*`. Unauthenticated → 302 login (or 403 webhook / 401 API). |
| **Impact** | Any compromised staff session can mutate stock and money documents. Same class of failure as the legacy “UI hid roles, URL didn’t” finding the rewrite claimed to fix. |
| **Recommendation** | Enforce Django permissions (or an explicit role matrix) on every mutator: intake, invoice create/stamp, returns process, hardware save/delete, admin. |

### C3 — `reference_id` not unique; duplicates already in data; API will break

| | |
|--|--|
| **Severity** | Critical (data + API correctness) |
| **Evidence** | Model: `reference_id` CharField indexed, not unique. Live: **160** duplicate groups, **359** rows; `ProductMaster.objects.get(reference_id__iexact='BNG-TTY')` → `MultipleObjectsReturned`. API `lookup_field = "reference_id"`. |
| **Impact** | Ambiguous catalogue identity; DRF detail route cannot reliably retrieve duplicates; clients can get 500s or wrong rows depending on queryset ordering. |
| **Recommendation** | Decide business rule (unique PJ vs supplier code collisions). Add constrained uniqueness where intended; fix API to use stable PK or disambiguate. |

### C4 — Stock transitions raceable; status rules not in DB

| | |
|--|--|
| **Severity** | Critical (integrity) |
| **Evidence** | Zero `select_for_update` in repo. `VALID_TRANSITIONS` is Python-only. Docstring claims DB CHECK via `choices=` — **false**; Postgres shows **0** check constraints on `inventory_productitem`. |
| **Impact** | Concurrent invoice/return/cancel can double-assign or leave inconsistent status. Raw SQL/admin/sync can write illegal statuses. |
| **Recommendation** | `select_for_update` on item rows inside every mutation; add `CheckConstraint`; consider partial unique “one open assignment per item”. |

---

## Full Findings

### Security

| ID | Sev | Finding | Confidence |
|----|-----|---------|------------|
| S1 | Crit | C1 password re-plant on sync | Confirmed |
| S2 | Crit | C2 flat authz | Confirmed |
| S3 | High | Sync token in query string; `?status=1` dumps last sync log without login | Confirmed |
| S4 | High | Developer account is permanent superuser; password re-applied on every worker boot when `DEV_ACCOUNT_PASSWORD` set (`ensure_developer_account` password_set logic) | Confirmed |
| S5 | High | `/dev/db-workbench/` exposes live MSSQL + Django schema to developer | Confirmed |
| S6 | Med | `DEBUG` defaults True; no `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` / HSTS in settings | Confirmed in code; prod Render env **not** directly inspected |
| S7 | Med | Unauthenticated `/media/` when `SERVE_MEDIA` and not S3 | Confirmed |
| S8 | Med | API key = full catalogue + prices; no scopes; throttle 2000/day | Confirmed |
| S9 | Med | Local `.env` present with MSSQL/AWS/SYNC secrets (gitignored) — machine compromise = all secrets | Confirmed keys exist, values not printed |
| S10 | Low | No MFA, lockout, or password-reset flow | Confirmed |
| S11 | Med | Legacy ASPX sources under `product assign with gold logic/` contradict README legal note “nothing…copied verbatim” | Confirmed files present and git-tracked |
| S12 | Med | Untracked `PJ_ERP_Full_Database_Export.xlsx` (~dump) not in `.gitignore` — commit hazard | Confirmed |

### Reliability

| ID | Sev | Finding | Confidence |
|----|-----|---------|------------|
| R1 | High | Sync lock uses **LocMemCache** — useless across gunicorn workers; daemon thread dies with worker | Confirmed |
| R2 | High | Webhook returns success before sync finishes; failures only in cache/logs | Confirmed |
| R3 | High | `django-q` installed/`Q_CLUSTER` set; **no worker process**; no `async_task` callers — ReserveAlert “scheduled job” cannot run | Confirmed |
| R4 | Med | WeasyPrint imported for invoice PDF but **not** in `requirements.txt` — PDF may fail on clean deploy | Confirmed |
| R5 | Med | Local tree behind origin by 4 commits (owner brief, data health, SyncRun, …) while carrying large dirty/untracked work — deploy/source-of-truth ambiguity | Confirmed via `git status` / `git log` |
| R6 | Med | Transfers: `IN_TRANSIT` never written; `execute` never called from HTTP | Confirmed |

### Data Integrity

| ID | Sev | Finding | Confidence |
|----|-----|---------|------------|
| D1 | Crit | C3 / C4 | Confirmed |
| D2 | High | Sync attaches assignment lines / overwrites payments without reconciling live `ProductItem.status` (0 ASSIGNED vs 206 COMPLETE invoices) | Confirmed locally |
| D3 | High | `invoice_number` not unique at DB; soft-delete intended for number reuse but `soft_delete()` never called | High |
| D4 | High | Intake: unlocked serial_no Max+1; apply then history write not one atomic unit | High |
| D5 | Med | Barcode lookup iexact / create may allow case variants on Postgres | Medium |
| D6 | Med | Display-slot allotment race (Python-only availability) | High |
| D7 | Med | README claimed 52 FKs / 133 indexes — live **64 FKs / 196 indexes** | Confirmed |

### Testing

| ID | Finding | Evidence |
|----|---------|----------|
| T1 | Full suite: **14 tests, OK** | Executed |
| T2 | No authz tests, no concurrency tests, no sync tests, no invoice/return integration tests in suite | Grep + suite run |
| T3 | Most `apps/*/tests.py` are stubs | File contents |
| T4 | Origin has richer `apps/core/tests.py` not present on this behind-main tree | `git diff HEAD origin/main` |

### Dependency / Supply Chain

| ID | Finding |
|----|---------|
| Dep1 | Pins in `requirements.txt` (Django 5.2.17, DRF, gunicorn, pymssql, storages, …) — good pinning |
| Dep2 | WeasyPrint missing from requirements but used |
| Dep3 | django-q2 present but unused at runtime |
| Dep4 | No lockfile beyond requirements.txt; no Dependabot/CI vulnerability scan in repo |
| Dep5 | No container base image to audit |

### Deployment / Infrastructure

| ID | Finding |
|----|---------|
| Deply1 | `Procfile`: `web: bash scripts/start.sh` only — no worker, no release phase file in-repo |
| Deply2 | No `.github/workflows`, no `render.yaml`, no Dockerfile |
| Deply3 | Production cookie/HTTPS settings not set in code — must be env/platform only (unverified on Render) |
| Deply4 | Dual catalog naming (`prod` profile) is **local snapshot**, not live tag11 — easy to confuse with Render DB |

### Documentation Drift

| Topic | Documentation | Code / Runtime | Conclusion |
|-------|---------------|----------------|------------|
| Hardware built? | README: still to build | Full UI + migrations + tests | **Docs wrong** |
| Permissions on every view | accounts models docstring | login_required only | **Docs wrong** |
| Status DB CHECK | inventory docstring | 0 check constraints | **Docs wrong** |
| FK/index counts | 52 / 133 | 64 / 196 | **Docs stale** |
| Payments/transfers “full” | README “what’s built” | No staff UI; Transfer.execute unused | **Overstated** |
| django-q for sync | settings + sync stub | Unused; webhook+thread instead | **Misleading** |
| No verbatim legacy copy | README legal note | `productassign.aspx(.cs)` in tree | **Contradicted** |
| `.env.example` complete | Implied | Missing MSSQL, SYNC token, DEV password | **Incomplete** |
| Local admin password | README mentions changeme123 | Sync **resets** it forever | **Dangerously incomplete** |

---

## Documentation Changes Made

| Document | Previous claim | Verified reality | Change | Confidence |
|----------|----------------|------------------|--------|------------|
| `README.md` | hardware/sync/hr/reporting “still not built”; vague completeness | hardware active; sync/hr/reporting stubs; api exists; payments/transfers partial | Rewrote “built / not built” sections; corrected FK/index counts; noted authz gap + sync password trap | Confirmed |
| `apps/accounts/models.py` | “enforced…on every view” | Only login_required / developer_required | Corrected docstring | Confirmed |
| `apps/inventory/models.py` | choices ⇒ DB CHECK | No CHECK in DB | Corrected docstring | Confirmed |
| `.env.example` | Incomplete env surface | settings read more vars | Documented missing keys (no secret values) | Confirmed |
| `.gitignore` | xlsx dumps not ignored | `PJ_ERP_Full_Database_Export.xlsx` untracked | Ignore export xlsx patterns | Confirmed |
| `PROJECT_WORKLOG.md` | — | This audit | Session entry appended | Confirmed |
| `SYSTEM-AUDIT-2026-09-11.md` | — | This report | Created | Confirmed |

---

## Architecture Drift

**Documented:** Faithful iadmin parity rebuild with Django permissions fixing legacy URL-bypass; FKs everywhere; transfers/payments as first-class modules; stubs for hardware/sync.

**Observed:** Developer-centric operational mirror with strong catalogue/invoice/returns/hardware UI; **permissions not wired**; transfers/payments incomplete; hardware already built; external API bolted on; sync via cron webhook + in-process thread; django-q vestigial; dual-write integrity not enforced.

---

## Dead / Orphaned Components

| Component | Status | Evidence |
|-----------|--------|----------|
| `apps.hr`, `apps.reporting`, `apps.sync` | Scaffold in INSTALLED_APPS | Empty models docstrings; 0 migrations |
| django-q worker | Configured, never started | Procfile / no callers |
| `Transfer.execute` / `execute_return` | Dead from HTTP | Only defined on model |
| `config.asgi` | Unused in deploy | gunicorn WSGI only |
| Tracker preview | Experimental | View docstring |
| `product assign with gold logic/` | Legacy reference, not executed | ASPX not routed |

---

## Unknowns (require human / prod access)

- Actual Render env: `DJANGO_DEBUG`, cookie flags, worker count, whether `SYNC_TRIGGER_TOKEN` / `DEV_ACCOUNT_PASSWORD` / `1001` exist in prod DB
- Whether cron still hits the webhook and how often
- Whether live iadmin remains source of truth (dual-write window)
- Whether untracked `apps/api` was intentionally withheld from git
- Conflict risk when rebasing/merging local work onto origin’s 4 commits
- Real load / race reproduction under concurrent scanners
- Contents of `PJ_ERP_Full_Database_Export.xlsx` (not opened beyond existence check)

---

## Recommended Remediation (priority)

1. **Critical security:** Remove `ensure_local_admin` from sync; rotate `1001` / any leaked sync tokens; audit Render for the password.
2. **Critical authz:** Role matrix + enforce on all mutators; stop equating `login_required` with authorization.
3. **Critical integrity:** Lock item rows; DB CHECKs; resolve `reference_id` uniqueness; stop sync from attaching lines without status reconciliation.
4. **Reliability:** Shared cache (Redis/DB) for sync lock; run sync out-of-band (management command / paid cron / django-q worker actually running); add WeasyPrint to requirements or remove PDF path.
5. **Source control:** Reconcile local vs `origin/main`; decide fate of untracked `apps/api` and photo assets; never commit xlsx dumps.
6. **Tests:** Authz, invoice concurrency, sync idempotency, API duplicate reference_id.
7. **Docs:** Keep this audit + worklog current; do not trust older README claims without re-verification.
8. **Cleanup (later):** Remove or quarantine legacy ASPX folder; drop unused django-q or wire it; soft-delete story vs cancel status.

---

## Evidence Ledger (selected)

| ID | Claim | Evidence | Method | Observed | Expected (docs/belief) | Diff | Sev | Conf | Action |
|----|-------|----------|--------|----------|------------------------|------|-----|------|--------|
| L1 | Sync resets 1001/changeme123 | `legacy_import.py`, `ensure_local_admin.py` | Code trace | Always called at end of import | One-time local bootstrap | Standing reset | Crit | Confirmed | Remove from sync |
| L2 | Permissions on every view | accounts docstring vs views grep + smoke | Code + Client | login only | RBAC | Lie | Crit | Confirmed | Fix docs + implement |
| L3 | Status CHECK in DB | docstring vs `pg_constraint` | SQL | 0 checks | CHECK exists | Lie | Crit | Confirmed | Fix docs + add constraint |
| L4 | reference_id unique enough for API | model + SQL + get() | SQL + ORM | 160 dup groups; MultipleObjectsReturned | Unique identity | Broken | Crit | Confirmed | Schema + API fix |
| L5 | Hardware not built | README vs urls/templates/migrations | Tree | Built | Unbuilt | Stale docs | High | Confirmed | Docs fixed |
| L6 | 52 FK / 133 indexes | README vs pg | SQL | 64 / 196 | 52 / 133 | Stale | Med | Confirmed | Docs fixed |
| L7 | django-q runs jobs | settings vs Procfile/grep | Code | Unused | Job runner | Vestigial | High | Confirmed | Wire or remove |
| L8 | LocMem sync lock | settings default CACHES | Runtime | LocMem | Cross-process lock | Broken under multi-worker | High | Confirmed | Shared cache |
| L9 | Test coverage meaningful | `manage.py test` | Executed | 14 pass | Broad ERP proof | Inadequate | High | Confirmed | Expand tests |
| L10 | Unauth staff routes redirect | Django test Client | Executed | 302/403/401 as appropriate | — | AuthN OK, AuthZ weak | — | Confirmed | — |

---

## Confidence Statement

**Directly verified:** Local Django check; migration plan; full test run (14); live Postgres constraint/index/row probes on `pj_erp_prod`; URL map; auth smoke with `force_login`; code paths for sync password reset, webhook, API auth, developer gate; git divergence.

**Inferred:** Multi-worker lock failure (LocMem + gunicorn); production impact if webhook enabled on Render; race outcomes under concurrency (logic implies, not load-tested).

**Not testable here:** Render dashboard config; production DB contents; live cron; opening the xlsx dump; network attack against production.

**Needs human confirmation:** Whether `1001`/`changeme123` exists on Render today; whether sync cron is active; intended uniqueness rule for `reference_id`; whether `apps/api` should be published; merge strategy for local vs origin.

---

*End of audit. Optimize for truth, not a clean bill of health.*
