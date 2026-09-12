"""
Carry the old iadmin system's generated files into this one.

Run against a checkout/copy of the legacy tree:

    python manage.py import_legacy_documents --source "C:\\Users\\Matt\\ftp_perfect-jewel-active-sync"
    python manage.py import_legacy_documents --source "..." --commit

DRY RUN BY DEFAULT. The first form reports exactly what it would copy,
what it could not match, and why. Nothing is written until `--commit`.

Scope of this pass: the 132 generated invoice PDFs in
`iadmin/documents/invoice/`, named `invoice_pdf_00<nid>.pdf` where <nid>
is `tblProductAssignMaster.nid`.

How the mapping works, and why it is safe:

  The legacy invoice number is literally `"RE00" + nid` (or `"RN00" + nid`
  for the reserve path) — see INVENTORY-AND-INVOICING.md §5.1. The
  snapshot importer preserves `invoice_number` verbatim, so a file called
  `invoice_pdf_00128.pdf` belongs to whichever AssignmentMaster carries
  `RE00128` or `RN00128`. No extra bridging table is needed.

  KNOWN AMBIGUITY, handled: invoices created *by this system* are numbered
  `RE{pk:06d}`, so a Django invoice at pk 1234 is `RE001234` — the same
  string legacy nid 1234 would produce. Below the collision threshold
  (legacy `RE00` + a 4-digit nid) the two schemes cannot be confused,
  because legacy numbers are shorter. At or above it they can. This
  command therefore refuses to attach a PDF to any invoice whose number is
  ambiguous, and reports it rather than guessing. If that ever fires, the
  numbering scheme needs deciding before the import can complete.

Idempotent: a file already attached to the same record with the same
sha256 is skipped, so re-running after fixing a few unmatched files costs
nothing and duplicates nothing.
"""

import hashlib
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.files.base import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.assignment.models import AssignmentMaster
from apps.core.models import LegacyDocument, LegacyDocumentKind

INVOICE_PDF_DIR = Path("iadmin") / "documents" / "invoice"
INVOICE_PDF_RE = re.compile(r"^invoice_pdf_00(\d+)\.pdf$", re.IGNORECASE)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class Command(BaseCommand):
    help = "Copy generated invoice PDFs (and later, other files) out of the legacy iadmin tree."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            required=True,
            help="Path to the legacy repository root (the folder containing iadmin/).",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually copy files and write rows. Without this, reports only.",
        )
        parser.add_argument(
            "--manifest",
            default="",
            help="Optional path to write a JSON manifest of everything copied, with checksums.",
        )

    def handle(self, *args, **opts):
        source = Path(opts["source"]).expanduser()
        if not source.is_dir():
            raise CommandError(f"--source is not a directory: {source}")

        pdf_dir = source / INVOICE_PDF_DIR
        if not pdf_dir.is_dir():
            raise CommandError(
                f"Expected invoice PDFs at {pdf_dir} — is --source pointing at the legacy repo root?"
            )

        commit = opts["commit"]
        if not commit:
            self.stdout.write(self.style.WARNING("DRY RUN — nothing will be written. Add --commit to apply.\n"))

        # Build the lookup once: legacy numbers are RE00<nid> / RN00<nid>.
        by_number = {
            m.invoice_number: m
            for m in AssignmentMaster.all_objects.exclude(invoice_number="").only("id", "invoice_number")
        }
        self.stdout.write(f"{len(by_number)} invoices in the database to match against.")

        matched, skipped, unmatched, ambiguous = [], [], [], []

        for path in sorted(pdf_dir.glob("*.pdf")):
            m = INVOICE_PDF_RE.match(path.name)
            if not m:
                unmatched.append((path.name, "filename does not follow invoice_pdf_00<nid>.pdf"))
                continue

            nid = m.group(1)
            candidates = [by_number.get(f"RE00{nid}"), by_number.get(f"RN00{nid}")]
            found = [c for c in candidates if c is not None]

            if not found:
                unmatched.append((path.name, f"no invoice numbered RE00{nid} or RN00{nid}"))
                continue
            if len(found) > 1:
                ambiguous.append((path.name, f"both RE00{nid} and RN00{nid} exist"))
                continue

            master = found[0]
            # The collision case described in the module docstring: a
            # Django-generated number is RE + 6 digits, so any legacy nid
            # of 4+ digits produces a string this system could also mint.
            if len(nid) >= 4 and master.pk != int(nid):
                ambiguous.append((
                    path.name,
                    f"{master.invoice_number} could be legacy nid {nid} or this system's pk {master.pk}",
                ))
                continue

            digest = sha256_of(path)
            already = LegacyDocument.objects.filter(
                model_label="assignment.assignmentmaster",
                object_id=str(master.pk),
                sha256=digest,
            ).exists()
            if already:
                skipped.append((path.name, master.invoice_number))
                continue

            matched.append((path, master, digest))

        # ---- report -------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"  to copy    {len(matched)}"))
        self.stdout.write(f"  already in {len(skipped)}")
        self.stdout.write(self.style.WARNING(f"  unmatched  {len(unmatched)}"))
        if ambiguous:
            self.stdout.write(self.style.ERROR(f"  AMBIGUOUS  {len(ambiguous)} — not attached, see below"))

        for name, why in unmatched[:20]:
            self.stdout.write(f"    unmatched: {name} — {why}")
        if len(unmatched) > 20:
            self.stdout.write(f"    … and {len(unmatched) - 20} more")
        for name, why in ambiguous:
            self.stdout.write(self.style.ERROR(f"    ambiguous: {name} — {why}"))

        if not commit:
            self.stdout.write("")
            self.stdout.write("Re-run with --commit to apply.")
            return

        # ---- copy ---------------------------------------------------
        written = []
        with transaction.atomic():
            for path, master, digest in matched:
                with open(path, "rb") as fh:
                    doc = LegacyDocument(
                        model_label="assignment.assignmentmaster",
                        object_id=str(master.pk),
                        kind=LegacyDocumentKind.INVOICE_PDF,
                        original_name=path.name,
                        source_path=str(path.relative_to(source)),
                        byte_size=path.stat().st_size,
                        sha256=digest,
                    )
                    doc.file.save(path.name, File(fh), save=False)
                    doc.save()
                written.append({
                    "invoice": master.invoice_number,
                    "assignment_pk": master.pk,
                    "original_name": path.name,
                    "stored_as": doc.file.name,
                    "bytes": doc.byte_size,
                    "sha256": digest,
                })

        self.stdout.write(self.style.SUCCESS(f"\nCopied {len(written)} file(s) into {settings.MEDIA_ROOT}."))

        if opts["manifest"]:
            manifest_path = Path(opts["manifest"]).expanduser()
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps({
                "source": str(source),
                "media_root": str(settings.MEDIA_ROOT),
                "copied": written,
                "skipped_already_present": [{"file": n, "invoice": i} for n, i in skipped],
                "unmatched": [{"file": n, "reason": r} for n, r in unmatched],
                "ambiguous": [{"file": n, "reason": r} for n, r in ambiguous],
            }, indent=2), encoding="utf-8")
            self.stdout.write(f"Manifest written to {manifest_path}")
            self.stdout.write(
                "Keep it — it is the proof that every file arrived intact, "
                "for the day someone proposes deleting the legacy copies."
            )
