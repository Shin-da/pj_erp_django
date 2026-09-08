#!/usr/bin/env bash
# Render / PaaS start: apply migrations (incl. Irys label data) then serve.
set -euo pipefail
python manage.py migrate --noinput
# Restore named label layouts (jefffffff). Does not wipe other templates.
python manage.py ensure_label_templates
# Create the developer login only when Render has DEV_ACCOUNT_PASSWORD set.
if [ -n "${DEV_ACCOUNT_PASSWORD:-}" ]; then
  python manage.py ensure_developer --password "$DEV_ACCOUNT_PASSWORD"
fi
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
