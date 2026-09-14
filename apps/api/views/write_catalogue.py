from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogue.models import ProductImage, ProductMaster, PhotoUploadBatch
from apps.catalogue.photo_staging import process_uploads, start_batch
from apps.catalogue.photos import (
    delete_all_product_images,
    delete_product_image,
    resolve_product_by_code,
    set_primary_image,
)

from ..mixins import EmployeeWriteMixin
from ..serializers import ProductImageSerializer, ProductMasterSerializer


def _product_payload(product, request):
    product = (
        ProductMaster.objects.select_related(
            "category", "currency", "supplier", "metal", "purity"
        )
        .prefetch_related("images")
        .get(pk=product.pk)
    )
    return ProductMasterSerializer(product, context={"request": request}).data


class ProductPhotoUploadView(EmployeeWriteMixin, APIView):
    """
    POST /api/v1/products/photos/

    multipart:
      - ``code`` (PJ/barcode) + ``images`` files — attach to that design
      - ``match_filename=1`` (optional) — ignore code; match each file's PJ token(s)
    """

    required_permission = "catalogue.can_upload_photos"
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploads = (
            request.FILES.getlist("images")
            or request.FILES.getlist("image")
            or request.FILES.getlist("photos")
        )
        if not uploads:
            return Response({"detail": "No image files uploaded."}, status=status.HTTP_400_BAD_REQUEST)

        match_filename = str(request.data.get("match_filename") or "").lower() in {
            "1", "true", "yes", "on",
        }
        if match_filename:
            batch = start_batch(
                user=request.user,
                mode=PhotoUploadBatch.Mode.API,
                source="API match_filename",
                request=request,
            )
            report = process_uploads(
                uploads, batch=batch, user=request.user, stage_unmatched=True, allow_no_code=True
            )
            return Response(
                {
                    "batch_id": report["batch_id"],
                    "matched_files": report["matched_files"],
                    "created": report["created"],
                    "staged": report["staged"],
                    "skipped": report["skipped"],
                    "failed": report["failed"],
                    "products_touched": report["products_touched"],
                    "unmatched": [{"name": n, "reason": r} for n, r in report["unmatched"]],
                    "images": ProductImageSerializer(
                        report.get("images", []), many=True, context={"request": request}
                    ).data,
                },
                status=status.HTTP_201_CREATED if report["created"] or report["staged"] else status.HTTP_200_OK,
            )

        code = (request.data.get("code") or "").strip()
        if not code:
            return Response({"detail": "code is required."}, status=status.HTTP_400_BAD_REQUEST)
        product = resolve_product_by_code(code)
        batch = start_batch(
            user=request.user,
            mode=PhotoUploadBatch.Mode.API,
            source="API products/photos",
            target_code=code,
            request=request,
        )
        report = process_uploads(
            uploads,
            batch=batch,
            user=request.user,
            force_code=code,
            stage_unmatched=True,
            allow_no_code=True,
        )
        payload = {
            "batch_id": report["batch_id"],
            "created": report["created"],
            "staged": report["staged"],
            "skipped": report["skipped"],
            "failed": report["failed"],
            "errors": [
                f"{n}: {r}" for n, r in report.get("unmatched", []) if report["failed"]
            ],
            "images": ProductImageSerializer(
                report.get("images", []), many=True, context={"request": request}
            ).data,
        }
        if product is not None:
            payload["product"] = _product_payload(product, request)
        return Response(
            payload,
            status=status.HTTP_201_CREATED if report["created"] or report["staged"] else status.HTTP_200_OK,
        )


class ProductImageDeleteView(EmployeeWriteMixin, APIView):
    """DELETE /api/v1/products/{product_id}/images/{image_id}/"""

    required_permission = "catalogue.can_upload_photos"

    def delete(self, request, product_id, image_id):
        image = get_object_or_404(ProductImage, pk=image_id, product_id=product_id)
        delete_product_image(image)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductImagePrimaryView(EmployeeWriteMixin, APIView):
    """POST /api/v1/products/{product_id}/images/{image_id}/primary/"""

    required_permission = "catalogue.can_upload_photos"

    def post(self, request, product_id, image_id):
        image = get_object_or_404(ProductImage, pk=image_id, product_id=product_id)
        set_primary_image(image)
        product = get_object_or_404(ProductMaster, pk=product_id)
        return Response({"product": _product_payload(product, request)})


class ProductImagesClearView(EmployeeWriteMixin, APIView):
    """DELETE /api/v1/products/{product_id}/images/ — remove every photo on the design."""

    required_permission = "catalogue.can_upload_photos"

    def delete(self, request, product_id):
        product = get_object_or_404(ProductMaster, pk=product_id)
        removed = delete_all_product_images(product)
        return Response({"removed": removed})
