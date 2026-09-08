from decimal import Decimal
import hmac
import io
import logging
import threading
import traceback

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Cast, Coalesce, Substr
from django.shortcuts import redirect, render
from django.conf import settings
from django.core.management import call_command
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.assignment.models import AssignmentLine, AssignmentMaster, InvoiceStatus, Reseller
from apps.core.models import SyncRun
from apps.catalogue.labels import subcategory_label
from apps.catalogue.models import Category, ProductMaster
from apps.inventory.models import ProductItem, StockStatus
from apps.locations.models import Location
from apps.payments.models import ResellerPayment
from apps.returns.models import ReserveAlert
from apps.tracker.models import TrackerSession
from apps.transfers.models import Transfer, TransferStatus
from apps.accounts.access import developer_required
from apps.core.data_map import (
    DJANGO_TABLES, FLOW, ID_TRAP, LEGACY_TABLES, NOT_COPIED, REL_CHAINS, STORES, SYNCED,
)
from apps.core.schema_browser import load_store, pick_table
from apps.core.sync_status import build_sync_report


def _pct(part, whole):
    if not whole:
        return 0
    return round(100.0 * part / whole, 1)


def _money(qs_filter):
    return (
        ProductItem.objects.filter(qs_filter).aggregate(total=Sum("product__selling_price"))["total"]
        or Decimal("0")
    )


def _zero_money():
    return Value(Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2))


def _latest_barcode_series(regex, digit_start, next_code):
    """
    Highest numeric barcode in a series (not lexicographic — PJ9 must not
    beat PJ24645). Returns the piece plus a suggested next code for operators
    entering new items by hand. Display-only; nothing is reserved in the DB.
    """
    item = (
        ProductItem.objects.filter(barcode__regex=regex)
        .annotate(seq=Cast(Substr("barcode", digit_start), IntegerField()))
        .select_related(
            "product",
            "product__category",
            "product__supplier",
            "product__metal",
            "location",
        )
        .order_by("-seq")
        .first()
    )
    if not item:
        return None
    return {
        "item": item,
        "seq": item.seq,
        "next_code": next_code(item.seq),
    }

def _net_line(prefix=""):
    """
    The SQL form of `AssignmentLine.calculate_line_total()` — unit price
    less the line's discount.

    Every money figure on this page used to be `Sum(unit_price)`, which
    silently ignored discounts: an invoice discounted 20% still showed at
    full price, so "invoiced" was overstated and the unpaid balance showed
    money outstanding that was never owed. `calculate_line_total()` stays
    the single source of truth for one line; this is the same arithmetic
    pushed into the database so a whole dashboard doesn't need a Python
    loop over every line.

    `prefix` is the relation path to AssignmentLine from whatever model is
    being annotated (e.g. "assignments__lines__" from Reseller).
    """
    return ExpressionWrapper(
        F(f"{prefix}unit_price")
        * (Value(Decimal("100")) - F(f"{prefix}discount_percent"))
        / Value(Decimal("100")),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


@login_required
def home(request):
    """
    Operational home — stock mix, collections, who has been invoiced.
    Numbers come from whichever local catalog DJANGO_DB_PROFILE points at,
    which is a mirror of iadmin, so every tile is "as of the last sync"
    (surfaced on the page via `last_sync`, not left to be assumed).

    Two figures on this page are routinely misread and are labelled in the
    template accordingly:

      * "Assigned" counts pieces flagged against an open reseller
        assignment. It is near zero on this data because Perfect Jewel
        moves stock to reseller-named *locations* by transfer instead of
        assigning it, so the honest answer to "what is out of the vault"
        is the By location table, not this tile.
      * The peso figures beside stock counts are sums of the catalogue's
        `selling_price` — list value of the tags, not revenue and not
        cost. Money that actually changed hands is the Sales band.
    """
    now = timezone.localtime()
    hour = now.hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    today = now.date()
    month_start = today.replace(day=1)

    status_rows = ProductItem.objects.values("status").annotate(n=Count("id"))
    status_counts = {row["status"]: row["n"] for row in status_rows}

    total_items = sum(status_counts.values())
    pending = status_counts.get(StockStatus.PENDING, 0)
    assigned = status_counts.get(StockStatus.ASSIGNED, 0)
    sold = status_counts.get(StockStatus.SOLD, 0)
    reserved = status_counts.get(StockStatus.RESERVED, 0)
    in_transit = status_counts.get(StockStatus.IN_TRANSIT, 0)

    available_value = _money(Q(status=StockStatus.PENDING))
    assigned_value = _money(Q(status=StockStatus.ASSIGNED))
    sold_value = _money(Q(status=StockStatus.SOLD))

    locations = list(
        Location.objects.annotate(
            item_count=Count("items"),
            available_count=Count("items", filter=Q(items__status=StockStatus.PENDING)),
            assigned_count=Count("items", filter=Q(items__status=StockStatus.ASSIGNED)),
            sold_count=Count("items", filter=Q(items__status=StockStatus.SOLD)),
        ).order_by("-item_count", "name")
    )
    loc_max = max((loc.item_count for loc in locations), default=0)
    for loc in locations:
        loc.bar_pct = _pct(loc.item_count, loc_max) if loc_max else 0
    locations_stocked = [loc for loc in locations if loc.item_count]
    locations_empty = [loc for loc in locations if not loc.item_count]

    categories = (
        Category.objects.annotate(item_count=Count("products__items"))
        .filter(item_count__gt=0)
        .order_by("-item_count")[:8]
    )

    subcategories = []
    for row in (
        ProductMaster.objects.exclude(subcategory="")
        .values("subcategory")
        .annotate(item_count=Count("items"))
        .order_by("-item_count")[:8]
    ):
        row["label"] = subcategory_label(row["subcategory"])
        subcategories.append(row)

    holders = list(
        Reseller.objects.annotate(
            items_held=Count(
                "assignments__lines__item",
                filter=Q(assignments__lines__item__status=StockStatus.ASSIGNED),
                distinct=True,
            )
        )
        .filter(items_held__gt=0)
        .order_by("-items_held", "name")[:8]
    )

    top_resellers = list(
        Reseller.objects.annotate(
            billed_lines=Count("assignments__lines"),
            billed_value=Sum(_net_line("assignments__lines__")),
        )
        .filter(billed_lines__gt=0)
        .order_by("-billed_value", "name")[:8]
    )

    money = DecimalField(max_digits=14, decimal_places=2)
    billed_sq = Subquery(
        AssignmentLine.objects.filter(master_id=OuterRef("pk"))
        .values("master_id")
        .annotate(t=Sum(_net_line()))
        .values("t")[:1],
        output_field=money,
    )
    paid_sq = Subquery(
        ResellerPayment.objects.filter(assignment_id=OuterRef("pk"))
        .values("assignment_id")
        .annotate(t=Sum("amount"))
        .values("t")[:1],
        output_field=money,
    )
    zero = _zero_money()

    recent_invoices = list(
        AssignmentMaster.objects.select_related("reseller")
        .annotate(
            line_count=Count("lines", distinct=True),
            billed=Coalesce(billed_sq, zero),
        )
        .order_by("-pk")[:8]
    )

    complete = AssignmentMaster.objects.filter(invoice_status=InvoiceStatus.COMPLETE).annotate(
        billed=Coalesce(billed_sq, zero),
        paid=Coalesce(paid_sq, zero),
    )
    unpaid_count = 0
    unpaid_balance = Decimal("0.00")
    for billed, paid in complete.values_list("billed", "paid"):
        billed = billed or Decimal("0")
        paid = paid or Decimal("0")
        if paid < billed:
            unpaid_count += 1
            unpaid_balance += billed - paid

    invoiced_value = (
        AssignmentLine.objects.filter(master__invoice_status=InvoiceStatus.COMPLETE).aggregate(
            total=Sum(_net_line())
        )["total"]
        or Decimal("0")
    )
    collected = ResellerPayment.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    collected_month = (
        ResellerPayment.objects.filter(paid_on__gte=month_start).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )

    invoice_rows = AssignmentMaster.objects.values("invoice_status").annotate(n=Count("id"))
    invoice_counts = {row["invoice_status"]: row["n"] for row in invoice_rows}

    # ---- Floor activity ------------------------------------------------
    # Scan sessions are written on every real tracker submit, so this is
    # the closest thing the system has to "what happened today". Shown
    # here because the tracker page only lists its own recent scans and
    # nothing else surfaces them.
    recent_scans = list(
        TrackerSession.objects.select_related("location", "created_by")
        .order_by("-scan_index")[:8]
    )
    scans_today = TrackerSession.objects.filter(created_at__date=today).count()
    pieces_scanned_today = (
        TrackerSession.objects.filter(created_at__date=today).aggregate(n=Sum("item_count"))["n"] or 0
    )

    # Transfers have no screen yet, so a pending count here is the only
    # place a stalled transfer becomes visible at all.
    transfers_pending = Transfer.objects.filter(status=TransferStatus.PENDING).count()

    # ---- Reserves about to lapse ---------------------------------------
    open_alerts = ReserveAlert.objects.filter(resolved_at__isnull=True).select_related(
        "item", "item__product", "reseller"
    )
    reserve_open_count = open_alerts.count()
    reserve_overdue = open_alerts.filter(expires_at__lt=now).count()
    reserve_alerts = list(open_alerts.order_by("expires_at")[:6])
    for alert in reserve_alerts:
        alert.is_overdue = alert.expires_at < now

    # Highest used PJ / PJGOLD — operators need these when tagging new pieces
    # so the next barcode does not collide. Two independent series.
    latest_pj = _latest_barcode_series(
        r"^PJ[0-9]+$",
        3,
        lambda n: f"PJ{n + 1}",
    )
    latest_pjgold = _latest_barcode_series(
        r"^PJGOLD[0-9]+$",
        7,
        lambda n: f"PJGOLD{n + 1:04d}",
    )

    context = {
        "greeting": greeting,
        "today_label": now.strftime("%A, %d %B %Y"),
        "month_label": now.strftime("%B"),
        "total_items": total_items,
        "pending": pending,
        "assigned": assigned,
        "sold": sold,
        "reserved": reserved,
        "in_transit": in_transit,
        "pending_pct": _pct(pending, total_items),
        "assigned_pct": _pct(assigned, total_items),
        "sold_pct": _pct(sold, total_items),
        "reserved_pct": _pct(reserved, total_items),
        "available_value": available_value,
        "assigned_value": assigned_value,
        "sold_value": sold_value,
        "locations_stocked": locations_stocked,
        "locations_empty": locations_empty,
        "categories": categories,
        "subcategories": subcategories,
        "holders": holders,
        "top_resellers": top_resellers,
        "recent_invoices": recent_invoices,
        "reseller_count": Reseller.objects.count(),
        "invoice_count": AssignmentMaster.objects.count(),
        "invoice_complete": invoice_counts.get(InvoiceStatus.COMPLETE, 0),
        "invoice_draft": invoice_counts.get(InvoiceStatus.DRAFT, 0),
        "invoice_cancelled": invoice_counts.get(InvoiceStatus.CANCELLED, 0),
        "invoiced_value": invoiced_value,
        "collected": collected,
        "collected_month": collected_month,
        "unpaid_count": unpaid_count,
        "unpaid_balance": unpaid_balance,
        "recent_scans": recent_scans,
        "scans_today": scans_today,
        "pieces_scanned_today": pieces_scanned_today,
        "transfers_pending": transfers_pending,
        "reserve_alerts": reserve_alerts,
        "reserve_open_count": reserve_open_count,
        "reserve_overdue": reserve_overdue,
        "latest_pj": latest_pj,
        "latest_pjgold": latest_pjgold,
        "last_sync": SyncRun.objects.filter(finished_at__isnull=False).first(),
    }
    return render(request, "core/home.html", context)


_SYNC_LOCK_KEY = "sync_legacy_webhook_running"
_SYNC_LAST_RESULT_KEY = "sync_legacy_webhook_last_result"
logger = logging.getLogger(__name__)


def _run_sync_in_background(trigger="webhook"):
    out = io.StringIO()
    run = SyncRun.objects.create(trigger=trigger)
    ok = False
    try:
        call_command("sync_legacy_mssql", stdout=out, stderr=out)
        ok = True
        result = f"OK {timezone.now().isoformat()}\n{out.getvalue()}"
        logger.info("sync_legacy_mssql (webhook) completed:\n%s", out.getvalue())
    except Exception:
        result = f"ERROR {timezone.now().isoformat()}\n{out.getvalue()}\n{traceback.format_exc()}"
        logger.exception("sync_legacy_mssql (webhook) failed")
    finally:
        SyncRun.objects.filter(pk=run.pk).update(
            finished_at=timezone.now(), ok=ok, summary=result[:20000]
        )
        cache.set(_SYNC_LAST_RESULT_KEY, result, timeout=60 * 60 * 48)
        cache.delete(_SYNC_LOCK_KEY)


@developer_required
def owner_brief(request):
    """Health numbers and confirmed bugs, for presenting to the owner."""
    from apps.core.owner_brief import (
        AS_OF,
        BOOKS,
        BUGS,
        CANNOT,
        FIXED,
        HEADLINE,
        VAULT,
        WINDOW,
    )

    return render(request, "core/owner_brief.html", {
        "as_of": AS_OF,
        "window": WINDOW,
        "headline": HEADLINE,
        "books": BOOKS,
        "vault": VAULT,
        "bugs": BUGS,
        "cannot": CANNOT,
        "fixed": FIXED,
    })


@developer_required
def data_health(request):
    """Read the live iadmin books and report what is wrong right now."""
    from apps.core.data_health import build_data_health

    return render(request, "core/data_health.html", {"health": build_data_health()})


@developer_required
def data_map(request):
    """How the legacy DB, this app, Render, and the Tiara sheet fit together."""
    return render(request, "core/data_map.html", {
        "stores": STORES,
        "flow": FLOW,
        "synced": SYNCED,
        "not_copied": NOT_COPIED,
        "legacy_tables": LEGACY_TABLES,
        "django_tables": DJANGO_TABLES,
        "rel_chains": REL_CHAINS,
        "id_trap": ID_TRAP,
        "active_profile": settings.DB_PROFILE,
        "active_name": settings.DATABASES["default"]["NAME"],
    })


@developer_required
def db_workbench(request):
    """Read-only table browser for live iadmin and the Django catalog."""
    store_id = request.GET.get("store") or "mssql"
    if store_id not in ("mssql", "django"):
        store_id = "mssql"
    refresh = request.GET.get("refresh") == "1"
    catalog = load_store(store_id, refresh=refresh)
    table = pick_table(catalog, request.GET.get("table") or "")
    return render(request, "core/db_workbench.html", {
        "store_id": store_id,
        "catalog": catalog,
        "table": table,
        "active_profile": settings.DB_PROFILE,
        "active_name": settings.DATABASES["default"]["NAME"],
    })


@developer_required
def db_sync_status(request):
    """Dev page: live MSSQL vs local pj_erp_prod / pj_erp_dev row counts."""
    report = build_sync_report()
    last_result = cache.get(_SYNC_LAST_RESULT_KEY)
    sync_running = cache.get(_SYNC_LOCK_KEY) is not None
    return render(
        request,
        "core/db_sync_status.html",
        {
            "report": report,
            "last_result": last_result,
            "sync_running": sync_running,
        },
    )


@developer_required
@require_POST
def db_sync_run(request):
    """Kick off sync_legacy_mssql in a background thread (same as the webhook)."""
    if not cache.add(_SYNC_LOCK_KEY, "1", timeout=60 * 20):
        messages.warning(request, "A sync is already running.")
        return redirect("core:db_sync_status")

    thread = threading.Thread(target=_run_sync_in_background, args=("dev page",), daemon=True)
    thread.start()
    messages.info(
        request,
        "Sync started into the active catalog "
        f"({settings.DB_PROFILE} / {settings.DATABASES['default']['NAME']}). "
        "Refresh in a minute to see updated counts.",
    )
    return redirect("core:db_sync_status")


def sync_legacy_webhook(request):
    """
    Free-tier-friendly cron trigger for `sync_legacy_mssql`.

    Meant to be pinged by an external scheduler (cron-job.org, same as the
    keep-alive pings already hitting this service) instead of paying for a
    Render Cron Job. Protected by a shared-secret token rather than login,
    since a scheduler can't authenticate as a user.

    Fire-and-forget: cron-job.org caps its request timeout at 30 seconds
    (even on top of Render's own gunicorn --timeout), well under how long
    a full sync can take, so the actual import runs in a background thread
    and this view returns immediately. Pass ?status=1 to check the last
    completed run's output instead of starting a new one.

    The cache lock stops two overlapping runs if the scheduler retries a
    request that looked slow from its side — not that a second run would
    corrupt anything (the importer is upsert-safe), it just wastes a DB
    connection.
    """
    token = request.GET.get("token", "")
    expected = getattr(settings, "SYNC_TRIGGER_TOKEN", "")
    if not expected or not hmac.compare_digest(token, expected):
        return HttpResponseForbidden("Forbidden")

    if request.GET.get("status"):
        last = cache.get(_SYNC_LAST_RESULT_KEY, "No run recorded yet.\n")
        running = cache.get(_SYNC_LOCK_KEY) is not None
        return HttpResponse(f"Currently running: {running}\n\nLast result:\n{last}", content_type="text/plain")

    if not cache.add(_SYNC_LOCK_KEY, "1", timeout=60 * 20):
        return HttpResponse("Sync already in progress, skipping this run.\n", content_type="text/plain")

    thread = threading.Thread(target=_run_sync_in_background, daemon=True)
    thread.start()

    return HttpResponse(
        "Sync started in the background. Check again with ?status=1 in a few minutes.\n",
        content_type="text/plain",
    )
