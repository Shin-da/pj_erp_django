from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogue.models import ProductImage, ProductMaster
from apps.catalogue.photos import (
    attach_uploaded_images,
    delete_product_image,
    resolve_product_by_code,
)

from ..mixins import EmployeeWriteMixin
from ..serializers import ProductImageSerializer, ProductMasterSerializer


class ProductPhotoUploadView(EmployeeWriteMixin, APIView):
    """
    POST /api/v1/products/photos/

    multipart: ``code`` (PJ/barcode) + ``images`` files (repeatable).
    """

    required_permission = "catalogue.can_upload_photos"
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        code = (request.data.get("code") or "").strip()
        if not code:
            return Response({"detail": "code is required."}, status=status.HTTP_400_BAD_REQUEST)
        product = resolve_product_by_code(code)
        if product is None:
            return Response(
                {"detail": f"No design found for {code!r}."},
                status=status.HTTP_404_NOT_FOUND,
            )
        uploads = request.FILES.getlist("images") or request.FILES.getlist("image")
        if not uploads:
            return Response({"detail": "No image files uploaded."}, status=status.HTTP_400_BAD_REQUEST)

        report = attach_uploaded_images(product, uploads)
        product = (
            ProductMaster.objects.select_related(
                "category", "currency", "supplier", "metal", "purity"
            )
            .prefetch_related("images")
            .get(pk=product.pk)
        )
        return Response(
            {
                "created": report["created"],
                "skipped": report["skipped"],
                "errors": report["errors"],
                "product": ProductMasterSerializer(product, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED if report["created"] else status.HTTP_200_OK,
        )


class ProductImageDeleteView(EmployeeWriteMixin, APIView):
    """DELETE /api/v1/products/{product_id}/images/{image_id}/"""

    required_permission = "catalogue.can_upload_photos"

    def delete(self, request, product_id, image_id):
        image = get_object_or_404(ProductImage, pk=image_id, product_id=product_id)
        delete_product_image(image)
        return Response(status=status.HTTP_204_NO_CONTENT)
