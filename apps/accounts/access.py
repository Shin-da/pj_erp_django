from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden


def is_developer(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_developer", False))


def developer_required(view):
    """Logged-in developer only. Everyone else gets 403, including on production."""

    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not is_developer(request.user):
            return HttpResponseForbidden("This page is for the developer account only.")
        return view(request, *args, **kwargs)

    return wrapped
