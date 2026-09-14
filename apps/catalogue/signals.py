"""Auto-claim floating photos when stock creates a matching PJ / barcode."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.catalogue.models import ProductMaster
from apps.catalogue.photo_staging import claim_staged_for_code
from apps.inventory.models import ProductItem


@receiver(post_save, sender=ProductItem)
def claim_photos_for_new_barcode(sender, instance: ProductItem, created, **kwargs):
    if not created:
        return
    code = (instance.barcode or "").strip()
    if not code:
        return
    claim_staged_for_code(code, instance.product)


@receiver(post_save, sender=ProductMaster)
def claim_photos_for_new_reference(sender, instance: ProductMaster, created, **kwargs):
    if not created:
        return
    code = (instance.reference_id or "").strip()
    if not code:
        return
    # Only claim when this looks like a PJ code — avoid random style names.
    if not code.upper().startswith("PJ"):
        return
    claim_staged_for_code(code, instance)
