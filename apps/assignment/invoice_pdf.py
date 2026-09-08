"""
Invoice PDF rendering.

Replaces `ResellerPaymentInvoice.aspx`'s SelectPdf HtmlToPdf pass. Same
approach — render the invoice as HTML, convert to A4 — with WeasyPrint
instead, so the layout stays a Django template that anyone can edit
rather than coordinates in code.

Three deliberate differences from the legacy document:

  1. **Paid and Balance are real.** The legacy page hardcoded
     `lblAmountPaid` to the full total and `lblBalance` to "PHP 0.000",
     and `inserttotal()` called `deleteoldpayment()` on every render — so
     every invoice it ever produced claimed paid-in-full with a zero
     balance, and viewing one destroyed its payment history. These come
     from `ResellerPayment` rows here, and nothing is deleted.

  2. **"Pondo" is gone.** It appears nowhere except the legacy markup and
     a hardcoded `"PHP 0.000"` — no column, no stored procedure, nothing
     in the database dump. It was a label with a constant. Add it back as
     a real field if the business says it means something.

  3. **Rendering does not stamp.** Opening the legacy invoice page set
     `invoice_status='complete'` as a side effect of `Page_Load`. Marking
     an invoice complete is an explicit action here; producing a PDF
     changes nothing.

Everything else is faithful: the branch banner and logo, the customer
block including "Res No.", the per-gram column that appears only for
gold, the four signature blocks, and the attachments checklist — that
checklist and those signatures are what make this a handover receipt
rather than a bill, which is why they're reproduced verbatim.
"""

from decimal import Decimal
from pathlib import Path

from django.template.loader import render_to_string


def media_uri(file_field):
    """
    WeasyPrint-friendly URI for a FileField.
    Local storage → file:// path (no round-trip to the app server).
    S3/R2 → https URL (`.path` raises NotImplementedError there).
    """
    if not file_field:
        return ""
    try:
        return Path(file_field.path).as_uri()
    except NotImplementedError:
        return file_field.url

# Categories whose lines show a "Price Per Gram" column. The legacy page
# decided this from `hndcategory.Value == "1" || == "4"` inside
# RowDataBound — and because it assigned to a shared column's Visible
# property per row, the LAST row silently decided it for the whole grid.
# Here it is a per-invoice decision made once, from any line qualifying.
GOLD_CATEGORY_CODES = {"JW", "MT"}


def build_invoice_context(master, *, payments=None):
    """
    Everything the template needs, resolved once. Kept separate from the
    render so the same context can drive an on-screen preview.
    """
    lines = list(
        master.lines.select_related(
            "item", "item__product", "item__product__category", "item__product__currency"
        ).order_by("id")
    )

    rows = []
    subtotal = Decimal("0")
    show_per_gram = False

    for n, line in enumerate(lines, start=1):
        product = line.item.product
        rate = product.effective_rate
        # The legacy invoice prints price * rate, not the raw catalogue
        # price. `calculate_line_total()` stays the source of truth for
        # the discounted amount; the rate is applied on top of it, in
        # that order, matching get_reseller_invoicedata.
        line_total = (line.calculate_line_total() * rate).quantize(Decimal("0.01"))
        unit_price = (line.unit_price * rate).quantize(Decimal("0.01"))
        subtotal += line_total

        is_gold = product.category and product.category.code in GOLD_CATEGORY_CODES
        if is_gold and product.metal_rate:
            show_per_gram = True

        rows.append({
            "n": n,
            "product_name": product.name,
            "product_code": product.reference_id or "",
            "barcode": line.item.barcode,
            "qty": 1,
            "net_weight": product.net_weight,
            # Legacy hardcodes this as N'g' in the stored procedure. It is
            # a constant, not a column — reproduced as one.
            "weight_unit": "g",
            "metal_rate": product.metal_rate if is_gold else None,
            "unit_price": unit_price,
            "line_total": line_total,
            "discount_percent": line.discount_percent,
        })

    if payments is None:
        payments = list(master.payments.all())
    paid = sum((p.amount for p in payments), Decimal("0"))

    location = master.reseller_location
    return {
        "master": master,
        "reseller": master.reseller,
        "location": location,
        "logo_uri": media_uri(location.logo) if location and location.logo else "",
        "rows": rows,
        "show_per_gram": show_per_gram,
        "subtotal": subtotal,
        "paid": paid,
        "balance": subtotal - paid,
        "payments": payments,
        "is_void": master.invoice_status == "CANCELLED",
    }


def render_invoice_html(master, *, payments=None):
    return render_to_string("assignment/invoice_pdf.html", build_invoice_context(master, payments=payments))


def render_invoice_pdf(master, *, payments=None, base_url=None):
    """
    Returns PDF bytes. Raises RuntimeError with a usable message if
    WeasyPrint isn't installed, rather than an ImportError traceback —
    this is called from a view a user clicked.
    """
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:  # OSError = GTK libs missing on Windows
        raise RuntimeError(
            "PDF rendering needs WeasyPrint. Install it with `pip install weasyprint`. "
            "On Windows it also needs the GTK3 runtime — if the import fails with a "
            f"libgobject/pango error, that's what's missing. Original error: {exc}"
        ) from exc

    html = render_invoice_html(master, payments=payments)
    return HTML(string=html, base_url=base_url).write_pdf()
