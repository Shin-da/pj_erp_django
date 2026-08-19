"""
NOT YET BUILT.

Will replace `excelexport.cs` (13 near-duplicate export methods across
three different Excel-generation techniques — a legacy HTML-rendered-as-
.xls hack, EPPlus, and an unused ClosedXML import, used inconsistently)
and the 679 historical `.xlsx` outputs under legacy `App_Data/` (treated
as historical artifacts per `CLAUDE.md`, not fixtures to replicate).
`openpyxl`/`pandas` only, one code path.
"""

from django.db import models  # noqa: F401
