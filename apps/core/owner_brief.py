"""
Owner-facing systems brief, developer login only.

Numbers were read 9 Sep 2026 from a local restore of production iadmin
(stock_rfid_dev, taken 13 Aug 2026). Read-only. There is no 12-month
history in that database — the system went live 10 Jul 2026.

This is the page to open when showing Perfect Jewel what the books
actually say, and which dashboard figures were wrong. It is not the
compensation argument.
"""

AS_OF = "13 Aug 2026 restore, queried 9 Sep 2026"
WINDOW = "10 Jul – 12 Aug 2026 (33 days of invoices)"

HEADLINE = (
    {
        "label": "Net invoiced",
        "value": "₱9,090,832",
        "sub": "101 invoices · cancellations excluded",
    },
    {
        "label": "Company-owned stock",
        "value": "₱28,371,918",
        "sub": "2,450 pieces · the rest is consignment",
    },
    {
        "label": "Catalogue sold / month",
        "value": "3.8%",
        "sub": "255 of 6,602 pieces in 33 days",
    },
    {
        "label": "Cash still outstanding",
        "value": "₱3,035,982",
        "sub": "33% of net invoices, at most 5 weeks old",
    },
)

BOOKS = (
    ("Gross invoiced", "122 invoices", "₱12,655,365"),
    ("Cancelled", "21 invoices · 28% of value", "₱3,564,533"),
    ("Net invoiced", "101 invoices", "₱9,090,832"),
    ("Cash collected", "81 payments", "₱6,054,850"),
    ("July net (10–31 Jul)", "57 invoices", "₱3,636,297"),
    ("August net (1–12 Aug)", "44 invoices", "₱5,454,534"),
)

VAULT = (
    ("Consignment — supplier-owned", "3,897 pieces", "₱184,340,995", "87%"),
    ("Purchased — company-owned", "2,450 pieces", "₱28,371,918", "13%"),
    ("Unsold total", "6,347 pieces", "₱212,712,913", "100%"),
)

BUGS = (
    {
        "title": "A ₱7.5 million sale that never happened",
        "figure": "₱7,547,626",
        "body": (
            "Assignment 97 (JUNNEL, 81 pieces, 5 August) is marked complete, "
            "with zero pieces sold and no invoice row at all. Anything that "
            "adds up assignment totals — including the live dashboard — "
            "overstates August by about ₱7.5 million."
        ),
    },
    {
        "title": "19 unpaid invoices the system was hiding",
        "figure": "35 shown, 54 real",
        "body": (
            "The unpaid tile trusted a running balance typed in on the last "
            "payment, not billed amount less every payment received. The "
            "gap is part of the ₱3,035,982 still outstanding."
        ),
    },
    {
        "title": "Every “today” and “this month” figure was on the wrong day",
        "figure": "Wrong clock",
        "body": (
            "Those queries used the database server’s clock, which is not "
            "Philippine time. For the last hours of every Manila day, the "
            "dashboard described a different day than the banner at the top "
            "of the same page."
        ),
    },
    {
        "title": "Peso amounts printed in Indian grouping",
        "figure": "₱17,45,425",
        "body": (
            "The server’s culture is en-IN, so ₱1,745,425 rendered as "
            "₱17,45,425. Read quickly that looks like 17 lakh, or a typo."
        ),
    },
    {
        "title": "“Active transfers: 291” was not 291 loads in transit",
        "figure": "291 counted",
        "body": (
            "It counted a column nothing in the system ever writes, so every "
            "transfer ever made counted as active. The stock had already arrived."
        ),
    },
    {
        "title": "The activity feed invented a midnight stocktake",
        "figure": "12:00 AM",
        "body": (
            "Some scan rows store a date and no time. Those printed as "
            "12:00 AM, so a large stocktake looked like it ran at midnight."
        ),
    },
)

CANNOT = (
    {
        "title": "No 12-month trend",
        "body": (
            "The system went live on 10 July 2026. 4,124 of 6,602 items were "
            "loaded that day. The earliest purchase date anywhere is 30 June 2026. "
            "Seasonality cannot be read from 33 days."
        ),
    },
    {
        "title": "Gross margin cannot be calculated",
        "body": (
            "Cost price is empty on all 6,602 rows. Supplier payable fields are "
            "blank on every row. Selling price over base price ranges from 0.36 "
            "to 29.30, so it is not a markup. If anyone quotes a margin, it did "
            "not come from this system."
        ),
    },
    {
        "title": "Two “sold” counts disagree",
        "body": (
            "One status field says 255 pieces sold; another on the same rows "
            "says 124. The 255 figure reconciles with invoice totals to within "
            "3%. The other is unexplained."
        ),
    },
    {
        "title": "Payment status is never updated",
        "body": (
            "All 128 assignments still read pending, paid or not. Only the "
            "payment table reflects cash actually received."
        ),
    },
)

FIXED = (
    {
        "where": "iadmin dashboard",
        "state": "Fixed in code · not confirmed uploaded",
        "body": (
            "Philippine date boundaries, Western peso grouping, transfers in "
            "the last 7 days instead of the dead pending column, unpaid as "
            "billed less payments, and timestamps that do not invent midnight. "
            "Those files are ready to FTP. They are not live until that upload."
        ),
    },
    {
        "where": "Django mirror",
        "state": "Fixed · depends on the last sync",
        "body": (
            "A daily sync was skipping status and location on existing pieces, "
            "so sold and location drifted from iadmin. Re-sync now refreshes "
            "those fields. The dashboard labels peso sums as list price, not "
            "as company value or as revenue."
        ),
    },
)
