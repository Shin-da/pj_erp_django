from apps.inventory.models import ProductItem
from apps.assignment.models import AssignmentMaster
from apps.payments.models import ResellerPayment, SupplierPayment, InvoiceCancellation
from apps.returns.models import ReturnRecord
from apps.tracker.models import TrackerScanItem
from apps.transfers.models import Transfer, TransferLine
from apps.catalogue.models import ProductMaster
from apps.locations.models import Location
from django.db.models import Count

print("--- ProductItem status breakdown ---")
for row in ProductItem.objects.values("status").annotate(n=Count("id")).order_by("-n"):
    print(f"  {row['status']:<10} {row['n']}")
print("  TOTAL:", ProductItem.objects.count())

print()
print("--- Cleared-tables sanity check (should all be 0) ---")
print("  AssignmentMaster:", AssignmentMaster.all_objects.count())
print("  ResellerPayment:", ResellerPayment.objects.count())
print("  InvoiceCancellation:", InvoiceCancellation.objects.count())
print("  SupplierPayment:", SupplierPayment.objects.count())
print("  ReturnRecord:", ReturnRecord.objects.count())
print("  TrackerScanItem:", TrackerScanItem.objects.count())
print("  Transfer:", Transfer.objects.count())
print("  TransferLine:", TransferLine.objects.count())

print()
print("--- Reimported counts ---")
print("  Location:", Location.objects.count())
print("  ProductMaster:", ProductMaster.objects.count())
print("  ProductItem:", ProductItem.objects.count())