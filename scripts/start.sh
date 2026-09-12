#!/usr/bin/env bash
# PaaS start (DigitalOcean App Platform / Render): migrate then serve.
set -euo pipefail
python manage.py migrate --noinput
# Restore named label layouts (jefffffff). Does not wipe other templates.
python manage.py ensure_label_templates
# Seed Vault Staff / Sales / Accounting group baselines (idempotent).
python manage.py setup_permission_groups
# Read DEV_ACCOUNT_PASSWORD inside Python. Do not pass it on the command
# line — a "!" in the password is otherwise dropped by the shell.
if [ -n "${DEV_ACCOUNT_PASSWORD:-}" ]; then
  python manage.py ensure_developer
fi
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --timeout 120
