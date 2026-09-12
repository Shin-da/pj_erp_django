"""
C2 fix (SYSTEM-AUDIT-2026-09-11.md): "No real authorization beyond
'logged in'". Groups/Permissions existed on the Employee model
(PermissionsMixin) but nothing in the business views ever checked one —
every screen was reachable by any logged-in employee.

This module is the single map between "a real thing an employee can do"
and the Django permission codename that gates it, organized into
categories for the Manage Employee Access screen (see
accounts/views.py::employee_access_edit and
templates/accounts/employee_access_edit.html). It exists so that page,
the setup_permission_groups management command, and the view decorators
all agree on the same list — add a permission here first, then wire it
into a model's Meta.permissions, then use it in @require_perm(...).

Design (per the owner's answers, 2026-09-12):
  - Only Owner/Admin (is_superuser) can grant or revoke anything here —
    see owner_admin_required in access.py. This is deliberately NOT a
    fixed role table: Group membership sets a starting point, but every
    individual's actual access is their own user_permissions, editable
    one person at a time (Django's normal Group-baseline +
    per-user-override model). That's what lets the 3-person Accounting
    team have staff-specific privilege levels instead of one shared
    "Accounting" permission set.
  - Sales / Showroom: view-only, always. They can search stock across
    ALL locations (the owner's answer — a showroom needs to say "yes we
    have that, held at HO" rather than turn a customer away), but never
    create or stamp an invoice, never process a return, never manage
    labels. No permission in this map is granted to that group beyond
    the implicit read-only views, which are still just @login_required
    (view-only screens were never the security gap — see the audit).
  - Vault Team (HO / main vault): full operational access — intake,
    invoicing, returns, printing.
  - Accounting (admin office, 3 people): higher privilege than Vault on
    the money side, but NOT handed out as one block permission — see
    above. setup_permission_groups seeds an "Accounting" Group with the
    invoicing + charge/credit permissions as a starting point; the owner
    still dials each person in individually from the Manage Employee
    Access screen.
"""

# (codename without app label, human label, one-line explanation shown in the UI)
PERMISSION_CATEGORIES = [
    {
        "key": "catalogue",
        "label": "Catalogue & Stock Intake",
        "app_label": "catalogue",
        "permissions": [
            (
                "can_intake_stock",
                "Bring in stock",
                "Create or update stock via Excel upload or the one-piece intake form.",
            ),
            (
                "can_upload_photos",
                "Upload product photos",
                "Attach photos to a design by PJ / barcode. Separate from stock intake — "
                "same login, different people and screen.",
            ),
        ],
    },
    {
        "key": "assignment",
        "label": "Invoicing / Assignment",
        "app_label": "assignment",
        "permissions": [
            (
                "can_create_invoice",
                "Assign stock to a reseller",
                "Create a new assignment (invoice) and add pieces to it.",
            ),
            (
                "can_stamp_invoice",
                "Stamp / finalize an invoice",
                "Mark a draft assignment as a complete, issued invoice.",
            ),
            (
                "can_add_charge",
                "Add charges / credits",
                "Add a manual charge or credit line to an invoice. Reserved for the accounting "
                "report feature described on the whiteboard — not yet wired to a view.",
            ),
        ],
    },
    {
        "key": "returns",
        "label": "Returns",
        "app_label": "returns",
        "permissions": [
            (
                "can_process_return",
                "Process returns",
                "Return, reserve, or confirm-sold a batch of scanned pieces.",
            ),
        ],
    },
    {
        "key": "hardware",
        "label": "Tag Printing",
        "app_label": "hardware",
        "permissions": [
            (
                "can_manage_labels",
                "Design label templates",
                "Create, edit, duplicate, or delete tag label templates.",
            ),
            (
                "can_print_label",
                "Print tags",
                "Send a tag to the Zebra printer for the first time.",
            ),
            (
                "can_reprint_label",
                "Re-print tags",
                "Print a tag again for a barcode that already has a successful print on file "
                "(the whiteboard's \"Tag Re-Print Approval\"). Granted separately from plain "
                "printing so a reprint always needs its own sign-off.",
            ),
        ],
    },
    {
        "key": "tracker",
        "label": "Stock Tracker (Balance Scans)",
        "app_label": "tracker",
        "permissions": [
            (
                "add_trackersession",
                "Run a balance scan",
                "Start an opening or closing tracker session (Django's built-in \"add\" permission "
                "on TrackerSession — no custom codename needed for this one).",
            ),
        ],
    },
]


def full_codename(app_label, codename):
    return f"{app_label}.{codename}"


def iter_all_permissions():
    """(full_codename, category_label, short_label, description) for every permission in the map."""
    for category in PERMISSION_CATEGORIES:
        for codename, short_label, description in category["permissions"]:
            yield (
                full_codename(category["app_label"], codename),
                category["label"],
                short_label,
                description,
            )


# Baseline Group -> full codenames, used only to seed a new employee's
# starting point (setup_permission_groups). Editing an employee's own
# user_permissions afterward is what actually controls their access —
# these lists are not re-applied automatically, so changing this map
# does not retroactively change anyone already set up.
GROUP_BASELINES = {
    "Vault Staff": [
        "catalogue.can_intake_stock",
        "assignment.can_create_invoice",
        "assignment.can_stamp_invoice",
        "returns.can_process_return",
        "hardware.can_print_label",
        "hardware.can_reprint_label",
        "tracker.add_trackersession",
    ],
    "Sales / Showroom": [
        # View-only by design — nothing granted here. The group still
        # exists so employees can be filed under it and so the Manage
        # Employee Access screen has somewhere to show "no extra access"
        # explicitly rather than leaving it ambiguous.
    ],
    "Accounting": [
        "assignment.can_create_invoice",
        "assignment.can_stamp_invoice",
        "assignment.can_add_charge",
        "returns.can_process_return",
    ],
}
