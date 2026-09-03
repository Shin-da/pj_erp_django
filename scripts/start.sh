#!/usr/bin/env bash
# Render / PaaS start: apply migrations (incl. Irys label data) then serve.
set -euo pipefail
python manage.py migrate --noinput
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
