"""
Supplier-consignment due dates.

Live iadmin stores purchase_type/due_date on tblproduct_master. There is no
alarm there. This module is the one place that decides what "due soon" means
so the home table, header bell, and reminder window cannot drift.

Warn only — nothing here returns stock or writes payments.
"""

from datetime import timedelta

from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from apps.catalogue.models import ProductMaster, PurchaseType
from apps.returns.models import ReserveAlert

NEAR_DAYS = 7
LIST_LIMIT = 8
BELL_LIMIT = 6


def due_horizon(today=None):
    today = today or timezone.localdate()
    return today, today + timedelta(days=NEAR_DAYS)


def consignment_due_qs(today=None):
    today, horizon = due_horizon(today)
    return ProductMaster.objects.filter(
        product_type=PurchaseType.CONSIGNMENT,
        is_active=True,
        due_date__isnull=False,
        due_date__lte=horizon,
    )


def decorate_due_rows(rows, today=None):
    today = today or timezone.localdate()
    for product in rows:
        days = (product.due_date - today).days if product.due_date else None
        product.days_left = days
        product.is_overdue = days is not None and days < 0
        product.is_due_today = days == 0
        if days is None:
            product.due_label = ""
        elif days < 0:
            product.due_label = f"Overdue {abs(days)}d"
        elif days == 0:
            product.due_label = "Due today"
        elif days == 1:
            product.due_label = "Due tomorrow"
        else:
            product.due_label = f"Due in {days}d"
    return rows


def consignment_due_summary(today=None, row_limit=LIST_LIMIT):
    today, horizon = due_horizon(today)
    base = ProductMaster.objects.filter(
        product_type=PurchaseType.CONSIGNMENT,
        is_active=True,
        due_date__isnull=False,
    )
    counts = base.aggregate(
        overdue=Count("id", filter=Q(due_date__lt=today)),
        due_today=Count("id", filter=Q(due_date=today)),
        soon=Count("id", filter=Q(due_date__gt=today, due_date__lte=horizon)),
    )
    overdue = counts["overdue"] or 0
    due_today = counts["due_today"] or 0
    soon = counts["soon"] or 0
    open_count = overdue + due_today + soon
    rows = []
    if open_count:
        rows = decorate_due_rows(
            list(
                base.filter(due_date__lte=horizon)
                .select_related("supplier")
                .order_by("due_date", "name", "id")[:row_limit]
            ),
            today=today,
        )
    return {
        "today": today,
        "near_days": NEAR_DAYS,
        "overdue_count": overdue,
        "today_count": due_today,
        "soon_count": soon,
        "open_count": open_count,
        "rows": rows,
    }


def header_notifications(today=None):
    """Bell rows: consignment dues first, then open reserve alerts."""
    today = today or timezone.localdate()
    consign = consignment_due_summary(today=today, row_limit=BELL_LIMIT)
    items = []
    for product in consign["rows"]:
        items.append({
            "kind": "consignment",
            "tone": "danger" if product.is_overdue else "warn",
            "title": f"{product.reference_id or product.name} — {product.due_label.lower()}",
            "meta": product.supplier.name if product.supplier_id else "Consignment",
            "url": reverse("catalogue:product_detail", args=[product.pk]),
            "unread": True,
        })

    reserves = list(
        ReserveAlert.objects.filter(resolved_at__isnull=True)
        .select_related("item", "item__product", "reseller")
        .order_by("expires_at")[:4]
    )
    for alert in reserves:
        expired = alert.expires_at.date() < today if alert.expires_at else False
        when = alert.expires_at.strftime("%b %d") if alert.expires_at else ""
        items.append({
            "kind": "reserve",
            "tone": "danger" if expired else "info",
            "title": f"{alert.item.barcode} reserved for {alert.reseller.name}",
            "meta": f"{'Lapsed' if expired else 'Until'} {when}".strip(),
            "url": reverse("catalogue:item_detail", args=[alert.item.barcode]),
            "unread": True,
        })

    return {
        "consignment": consign,
        "items": items,
        "count": consign["open_count"] + len(reserves),
        "reserve_count": len(reserves),
    }
