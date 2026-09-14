"""
Copy the almarphoto uploads folder into a new folder where every file is
renamed down to just its PJ product code, so the result can be uploaded to
DigitalOcean Spaces directly (no Django import, no product matching).

Source files look like:

    1784518482_PJ22171 183,645 18K YG 0.35 10.68g.JPG
    1784686575_2340_E-PJ22155 111,227 18K 4.81g R-PJ22154 100,139 18K PG 5.35g.JPG

This pulls out every ``PJ<digits>`` token (same regex as
apps/catalogue/management/commands/import_product_images.py) and writes:

    PJ22171.jpg
    PJ22155.jpg   (copy of the same file)
    PJ22154.jpg   (copy of the same file)

A code that shows up on more than one source file (different angles of the
same item) keeps every photo, numbered PJ22171.jpg, PJ22171-2.jpg,
PJ22171-3.jpg, ... File extensions are lower-cased; nothing else about the
image bytes is touched.

Nothing is written until --apply is passed — without it this only prints a
summary and writes the unmatched/manifest reports.

Usage (from pj-erp, with venv activated or venv\\Scripts\\python.exe present):

    python scripts/strip_pj_filenames.py
    python scripts/strip_pj_filenames.py --apply
    python scripts/strip_pj_filenames.py --apply --source "C:\\xampp\\htdocs\\almarphoto\\uploads" --dest "C:\\xampp\\htdocs\\almarphoto\\uploads_pj_named"
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from pathlib import Path

# Same pattern as import_product_images.py: 4-6 digit PJ codes, optional
# single-letter category prefix (B-/N-/E-/P-/R-) discarded. Lookbehind
# instead of \b because real filenames are "<timestamp>_PJ22171 ..." and
# "_" is a word char, so \b never fires there.
CODE_RE = re.compile(r"(?:(?<![A-Za-z])[A-Z]-)?(?<![A-Za-z])(PJ\d{4,6})\b", re.IGNORECASE)
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def codes_in(filename: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in CODE_RE.finditer(filename):
        code = m.group(1).upper()
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def build_plan(files: list[Path]) -> tuple[list[tuple[Path, str]], list[tuple[str, str]]]:
    """Returns (plan, unmatched). plan is [(source_path, dest_filename), ...]."""
    plan: list[tuple[Path, str]] = []
    unmatched: list[tuple[str, str]] = []
    next_index: dict[str, int] = {}

    for src in files:
        codes = codes_in(src.name)
        if not codes:
            unmatched.append((src.name, "no PJ code in filename"))
            continue
        ext = src.suffix.lower()
        for code in codes:
            n = next_index.get(code, 1)
            next_index[code] = n + 1
            dest_name = f"{code}{ext}" if n == 1 else f"{code}-{n}{ext}"
            plan.append((src, dest_name))

    return plan, unmatched


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rename almarphoto photos down to their PJ code for direct DO Spaces upload."
    )
    parser.add_argument(
        "--source",
        default=r"C:\xampp\htdocs\almarphoto\uploads",
        help="Folder of original photos (default: %(default)s).",
    )
    parser.add_argument(
        "--dest",
        default="",
        help="Folder to write PJ-named copies into "
        "(default: <source>_pj_named, next to --source).",
    )
    parser.add_argument("--apply", action="store_true", help="Actually copy files. Without this, dry-run only.")
    parser.add_argument("--report-dir", default="", help="Where to write manifest/unmatched CSVs (default: --dest).")
    args = parser.parse_args()

    source = Path(args.source).expanduser()
    if not source.is_dir():
        parser.error(f"Not a folder: {source}")

    dest = Path(args.dest).expanduser() if args.dest else source.parent / f"{source.name}_pj_named"
    report_dir = Path(args.report_dir).expanduser() if args.report_dir else dest

    files = sorted(
        p for p in source.iterdir()
        if p.is_file() and p.suffix.lower() in IMG_EXT
    )
    plan, unmatched = build_plan(files)

    dupe_codes = sorted({name.split("-")[0] for _, name in plan if "-" in Path(name).stem})

    print(f"Source       : {source}  ({len(files)} image file(s))")
    print(f"Dest         : {dest}")
    print(f"Mode         : {'APPLY (copies files)' if args.apply else 'DRY RUN (report only)'}")
    print(f"Files matched: {len(plan)} planned copies from {len(files) - len(unmatched)} source file(s)")
    print(f"Codes with >1 photo: {len(dupe_codes)}")
    print(f"Unmatched (no PJ code): {len(unmatched)}")
    print()

    if args.apply:
        dest.mkdir(parents=True, exist_ok=True)
        for src, dest_name in plan:
            shutil.copy2(src, dest / dest_name)
        print(f"Copied {len(plan)} file(s) into {dest}")

    report_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = report_dir / "_manifest.csv"
    with open(manifest_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["source_filename", "dest_filename"])
        w.writerows((src.name, dest_name) for src, dest_name in plan)
    print(f"Manifest written: {manifest_path}")

    if unmatched:
        unmatched_path = report_dir / "_unmatched.csv"
        with open(unmatched_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["filename", "reason"])
            w.writerows(unmatched)
        print(f"Unmatched report : {unmatched_path}")
        for name, why in unmatched[:15]:
            print(f"  - {name}  ({why})")
        if len(unmatched) > 15:
            print(f"  ... and {len(unmatched) - 15} more")

    if not args.apply:
        print()
        print("Dry run only — re-run with --apply to write the renamed copies.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
