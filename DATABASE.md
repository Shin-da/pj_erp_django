# Local Postgres catalogs (dev / prod snapshot)

Two PostgreSQL databases on this machine, both filled from the **FTP MSSQL
snapshot** (`stock_rfid_backup.sql`). Neither one is the live `tag11.in`
server. Switching never touches production SQL Server.

| Profile | Catalog | Use |
|---------|---------|-----|
| `dev` | `pj_erp_dev` | Working copy. Mutate while building. |
| `prod` | `pj_erp_prod` | Frozen snapshot of real catalogue, resellers, invoices, payments. |

## Switch

In gitignored `.env`:

```
DJANGO_DB_PROFILE=dev
# or
DJANGO_DB_PROFILE=prod
```

Restart `runserver`. The top bar shows **DEV** (green) or **PROD SNAPSHOT** (red).

Same credentials (`DB_USER` / `DB_PASSWORD`) for both catalogs.

`pj_dev` cannot create databases. The setup script logs in once as the Postgres
superuser (`postgres`) to `ALTER USER pj_dev CREATEDB` and create any missing
catalog. If that login fails, set `$env:PG_SUPERUSER_PASSWORD` to the password
from the PostgreSQL installer, then re-run the script.

`clone_prod_to_dev` never drops a database — it wipes the dest schema and
restores a dump. Both catalogs must already exist.

## Load the snapshot

From `pj-erp` with the venv active:

```powershell
powershell -File scripts\setup_databases.ps1
```

Or step by step:

```powershell
# 1. One-time, as Postgres superuser (installer password):
psql -U postgres -h localhost -c "ALTER USER pj_dev WITH CREATEDB;"
psql -U postgres -h localhost -c "CREATE DATABASE pj_erp_dev OWNER pj_dev;"
psql -U postgres -h localhost -c "CREATE DATABASE pj_erp_prod OWNER pj_dev;"

# 2. Schema + data into the frozen catalog
$env:DJANGO_DB_PROFILE = "prod"
python manage.py migrate
python manage.py import_mssql_snapshot --flush

# 3. Clone that into the working copy
python manage.py clone_prod_to_dev --yes
# If clone fails (no CREATEDB), set DJANGO_DB_PROFILE=dev and re-run migrate + import.

# 4. Day-to-day: leave DJANGO_DB_PROFILE=dev
```

`import_mssql_snapshot` reads `LEGACY_SQL_DUMP` (the SSMS script of `stock_rfid`).
It maps real lookup names (jewellery type, sub-category, vendor, currency, metal,
purity) instead of `Vendor 16` placeholders.

**Not imported:** employee passwords, SSNs, bank accounts, salaries, tracker
sessions, transfer history. A local login `1001` / `changeme123` is created
only if no superuser exists yet.

## Reset the working copy

```powershell
python manage.py clone_prod_to_dev --yes
```

or re-import into `dev` with `--flush`.
