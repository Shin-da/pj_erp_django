"""
NOT YET BUILT.

Will replace `Global_Syncdata.cs` (Tiara/Irys catalogue sync).

Confirmed, must-fix-before-porting findings:
  - The sync URL is built with `&replace=true` literally in the request —
    every sync call replaces Tiara's entire remote catalogue rather than
    updating incrementally.
  - `getbarcodes()` reads `WHERE nid < 15` — a hardcoded ~14-row test
    limit left in otherwise-production code.
  - The Tiara API key is hardcoded in three separate places in the legacy
    source (`Global_Syncdata.cs`, `Global.asax.cs`, `test.aspx.cs`).
  - `iadmin/test.aspx.cs` reimplements the Tiara client independently
    with its own hardcoded key rather than calling the shared sync
    module — do not build two sync paths here; there is exactly one.

Use `django_q` (already installed, see `Q_CLUSTER` in settings) for the
job queue instead of the legacy `ThreadPool.QueueUserWorkItem` polling
loop with an unbounded log file. Every sync job model should carry an
explicit `dry_run` flag defaulting to True.
"""

from django.db import models  # noqa: F401
