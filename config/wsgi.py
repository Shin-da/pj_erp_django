"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

# Create the developer login when the web process boots, even if Render
# starts gunicorn without scripts/start.sh. Password stays in the env var.
def _ensure_developer_login():
    import logging

    if not os.environ.get("DEV_ACCOUNT_PASSWORD", "").strip():
        return
    try:
        from apps.accounts.developer import ensure_developer_account

        ensure_developer_account()
    except Exception:
        import traceback

        logging.getLogger("apps.accounts").exception(
            "Could not create the developer login on startup."
        )
        traceback.print_exc()
        print("ensure_developer: failed on startup", flush=True)


_ensure_developer_login()
