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


def is_owner_admin(user) -> bool:
    """
    Owner/Admin tier for the C2 permissions fix (SYSTEM-AUDIT-2026-09-11.md).

    Deliberately Django's own `is_superuser`, not a new flag: a superuser
    already bypasses every `has_perm()` check, which is exactly the
    "Owner/Admin sees and can grant everything" behaviour the owner asked
    for. Kept separate from `is_developer` on purpose — that flag only
    gates the /dev/ database tools (an unrelated axis; a developer is not
    automatically an Owner/Admin and vice versa).
    """
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False))


def owner_admin_required(view):
    """Logged-in Owner/Admin only. Used to gate the Manage Employee Access screen."""

    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not is_owner_admin(request.user):
            return HttpResponseForbidden("This page is for Owner/Admin accounts only.")
        return view(request, *args, **kwargs)

    return wrapped


def require_perm(codename):
    """
    Gate a view behind one Django permission codename, e.g.
    "assignment.can_create_invoice". A superuser (Owner/Admin) always
    passes. Everyone else needs the permission on their own
    `user_permissions` OR via a Group they belong to — Django's
    `has_perm()` already checks both, which is exactly the "Group gives a
    baseline, individual overrides adjust it" model the owner asked for.

    This is the actual fix for C2: replaces "any logged-in employee can
    do this" with "only an employee who has been granted this specific
    permission can do this." Stack it under @login_required is not
    needed separately — this decorator already requires login first.
    """

    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not (request.user.is_superuser or request.user.has_perm(codename)):
                return HttpResponseForbidden(
                    "You don't have permission to do this. Ask Owner/Admin to grant access "
                    f"({codename}) if you think you should."
                )
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def require_any_perm(*codenames):
    """
    Like require_perm, but any one of the listed codenames is enough.
    Used where the same screen serves two related privileges (e.g. first
    print vs reprint on the tag printer page).
    """

    if not codenames:
        raise ValueError("require_any_perm needs at least one permission codename")

    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            user = request.user
            if user.is_superuser or any(user.has_perm(c) for c in codenames):
                return view(request, *args, **kwargs)
            listed = ", ".join(codenames)
            return HttpResponseForbidden(
                "You don't have permission to do this. Ask Owner/Admin to grant access "
                f"({listed}) if you think you should."
            )

        return wrapped

    return decorator
