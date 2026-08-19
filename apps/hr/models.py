"""
NOT YET BUILT.

Will hold `EmployeeProfile` (one-to-one with `accounts.Employee`) for the
sensitive PII the legacy `tblemployee` stored in the same row as the
login password: ssn, bank/account/ifsc, salary, dob, address, emergency
contacts, blood group, marital status (confirmed columns,
IADMIN-SYSTEM-REFERENCE.md §9b.4 — flagged there as the single most
urgent security finding in the whole system: a table with plaintext
passwords ALSO holding government IDs and salary). Keeping this in a
separate app/table from `accounts.Employee` means read access to it can
be permissioned independently of the ability to authenticate as staff.

Also will replace the `AttendanceMasterPage` cluster
(`PunchLogReport.aspx`, `AttendanceReport.aspx`, `my_attendance.aspx`).
Note: **no code anywhere in the legacy app writes `tbldevice_log`** — an
unidentified external process populates biometric punches
(HARDWARE-INTEGRATIONS.md §8). A rebuild does not resolve that; it just
needs to keep treating that table/feed as read-only from an external
source, same as today, until the writer is identified.
"""

from django.db import models  # noqa: F401
