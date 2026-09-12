"""Shared status-badge rendering, so every table renders the same pill for the same status.

Before this existed, the PENDING/ASSIGNED/SOLD/RESERVED/IN_TRANSIT if/elif chain was
copy-pasted across item_detail, product_detail, location_detail and search (verbatim)
plus invoice_list (with a differently-colored fallback) — five-plus places to keep in
sync by hand. Route any new stock-status display through `stock_status_pill` instead.
"""

from django import template
from django.utils.html import format_html

register = template.Library()

_STOCK_PILL = {
    "PENDING": ("pill-ok", "Available"),
    "ASSIGNED": ("pill-info", "Assigned"),
    "SOLD": ("pill-neutral", "Sold"),
    "RESERVED": ("pill-warn", "Reserved"),
    "IN_TRANSIT": ("pill-violet", "In transit"),
}


@register.filter(name="stock_status_pill")
def stock_status_pill(item):
    """Render the stock-status badge for an object exposing `.status` / `.get_status_display()`."""
    if item is None:
        return ""
    status = getattr(item, "status", None)
    css_class, label = _STOCK_PILL.get(status, (None, None))
    if css_class is None:
        css_class = "pill-neutral"
        label = item.get_status_display() if hasattr(item, "get_status_display") else status
    return format_html('<span class="pill {}">{}</span>', css_class, label)
