# Deploy Perfect Jewel ERP on DigitalOcean

Target: **App Platform** + **Managed Postgres** + **Spaces** (media).  
Build/start scripts are the same ones Render used (`scripts/build.sh`, `scripts/start.sh`).

Spec file: [`.do/app.yaml`](.do/app.yaml)

---

## 1. Create Spaces (photos / uploads)

1. DigitalOcean → **Spaces** → Create bucket (e.g. `pj-erp-media`) in **sgp1** (or your region).
2. Enable **CDN** optional; for public product images, make the bucket (or objects) publicly readable, or use a Spaces CDN hostname.
3. **API** → Spaces Keys → Generate Access Key + Secret.
4. Note:
   - Endpoint: `https://sgp1.digitaloceanspaces.com` (match your region)
   - Custom domain / CDN host: `pj-erp-media.sgp1.digitaloceanspaces.com` (or your CDN)

---

## 2. Create the App

### Option A — Control Panel (recommended first time)

1. **Apps** → Create App → GitHub → `Shin-da/pj_erp_django` → branch `main`.
2. Autodetect Python. Set:
   - **Build command:** `bash scripts/build.sh`
   - **Run command:** `bash scripts/start.sh`
3. **Add resource** → Database → PostgreSQL (Dev is OK to start; use a production cluster for live).
4. Add env vars (see §3). Bind `DATABASE_URL` = `${db.DATABASE_URL}` (use your DB component name).
5. Deploy.

### Option B — App Spec

1. Edit `.do/app.yaml`: region, instance size, Spaces bucket name, secrets.
2. `doctl apps create --spec .do/app.yaml`  
   or paste the YAML under App → Settings → App Spec.

---

## 3. Environment variables (required)

| Key | Value |
|-----|--------|
| `DATABASE_URL` | `${db.DATABASE_URL}` (bind to the Postgres component) |
| `DJANGO_SECRET_KEY` | long random secret (**Encrypt**) |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `${APP_DOMAIN}` or `your.app.ondigitalocean.app,your.custom.domain` |
| `CSRF_TRUSTED_ORIGINS` | `https://your.app.ondigitalocean.app` (must include `https://`) |
| `DJANGO_TIME_ZONE` | `Asia/Manila` |
| `DB_SSLMODE` | `require` |
| `AWS_STORAGE_BUCKET_NAME` | Spaces bucket name |
| `AWS_ACCESS_KEY_ID` | Spaces key (**Encrypt**) |
| `AWS_SECRET_ACCESS_KEY` | Spaces secret (**Encrypt**) |
| `AWS_S3_ENDPOINT_URL` | `https://sgp1.digitaloceanspaces.com` |
| `AWS_S3_REGION_NAME` | `sgp1` |
| `AWS_S3_CUSTOM_DOMAIN` | `bucket.sgp1.digitaloceanspaces.com` (no `https://`) |
| `AWS_QUERYSTRING_AUTH` | `False` for public-read objects |

Optional:

| Key | Purpose |
|-----|---------|
| `DEV_ACCOUNT_PASSWORD` | Creates/updates `dev` employee on boot |
| `SYNC_TRIGGER_TOKEN` | `/internal/sync-legacy-mssql/?token=` |
| `LEGACY_MSSQL_*` | Live iadmin read-sync |

Local dual-DB profile (`DJANGO_DB_PROFILE` / `DB_NAME_*`) is **ignored** when `DATABASE_URL` is set.

---

## 4. After first successful deploy

Console → your app → **Console** (or one-off job):

```bash
python manage.py setup_permission_groups   # also runs on every start now
python manage.py createsuperuser           # or ensure_developer if DEV_ACCOUNT_PASSWORD set
python manage.py create_api_client "do-prod"
```

Then in the web UI: **Manage Employee Access** — put vault staff on Vault Staff / grant perms.

If you have an existing local/Render `media/` tree to preserve:

```bash
# From a machine with media/ + the same AWS_* env:
python manage.py upload_local_media
```

---

## 5. Large photo uploads

App Platform / proxies may cap body size. For bulk camera drops:

- Prefer Spaces direct uploads later if limits bite.
- Or raise limits on a Droplet/nginx setup (`client_max_body_size`).

App settings already allow large Django request bodies (`DATA_UPLOAD_MAX_MEMORY_SIZE`).

---

## 6. Custom domain + HTTPS

App → Settings → Domains → add domain.  
Update `DJANGO_ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` to include the new host (`https://…` for CSRF).

---

## 7. Cron (legacy MSSQL sync)

Use [cron-job.org](https://cron-job.org) (or DO Functions) to GET:

`https://YOUR_APP/internal/sync-legacy-mssql/?token=SYNC_TRIGGER_TOKEN`

Same pattern as Render.

---

## Smoke checklist

- [ ] Login page loads over HTTPS  
- [ ] `DJANGO_DEBUG=False` (no debug toolbar / tracebacks to clients)  
- [ ] Create product photo → URL on Spaces hostname  
- [ ] Invoice/returns forbidden for Sales user; OK for Vault  
- [ ] `GET /api/v1/products/` with Api-Key → 200  
- [ ] `POST /api/v1/auth/token/` → Employee token works  

---

## Droplet instead of App Platform?

Possible (nginx + gunicorn + systemd + Managed DB + Spaces), but not scripted in-repo yet. Prefer App Platform unless you need SSH-level control or larger upload proxies.
