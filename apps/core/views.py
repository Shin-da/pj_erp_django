from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def home(request):
    """
    Placeholder landing page. The legacy system routed post-login into one
    of nine role-scoped master pages (sitemaster/stockmaster/reportsmaster/
    etc.) — this will grow into an equivalent role-aware dashboard once
    more apps are built out. For now it just proves auth + routing work.
    """
    return render(request, "core/home.html")
