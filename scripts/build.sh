#!/usr/bin/env bash
# Render / PaaS build: install deps + collect static for WhiteNoise.
set -euo pipefail
pip install -r requirements.txt
python manage.py collectstatic --noinput
