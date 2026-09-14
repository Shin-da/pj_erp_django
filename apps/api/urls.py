from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import IsAuthenticated
from rest_framework.routers import DefaultRouter

from .authentication import ApiKeyAuthentication
from .views import (
    AssignmentMasterViewSet,
    CategoryViewSet,
    CurrencyViewSet,
    LabelPrintLogViewSet,
    LabelTemplateViewSet,
    LocationViewSet,
    MetalViewSet,
    ProductItemViewSet,
    ProductViewSet,
    PurityViewSet,
    ResellerGroupViewSet,
    ResellerLocationViewSet,
    ResellerViewSet,
    ReserveAlertViewSet,
    ReturnRecordViewSet,
    SupplierViewSet,
    TrackerSessionViewSet,
)
from .views.auth import ObtainEmployeeTokenView, RevokeEmployeeTokenView
from .views.write_assignment import InvoiceCreateView, InvoiceStampView
from .views.write_catalogue import (
    ProductImageDeleteView,
    ProductImagePrimaryView,
    ProductImagesClearView,
    ProductPhotoUploadView,
)
from .views.write_ops import (
    LabelPrintLogCreateView,
    TrackerOpeningCreateView,
    TrackerValidateView,
)
from .views.write_returns import ReturnProcessView

app_name = "api"

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("categories", CategoryViewSet, basename="category")
router.register("currencies", CurrencyViewSet, basename="currency")
router.register("metals", MetalViewSet, basename="metal")
router.register("purities", PurityViewSet, basename="purity")
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("locations", LocationViewSet, basename="location")
router.register("items", ProductItemViewSet, basename="item")
router.register("reseller-groups", ResellerGroupViewSet, basename="reseller-group")
router.register("reseller-locations", ResellerLocationViewSet, basename="reseller-location")
router.register("resellers", ResellerViewSet, basename="reseller")
router.register("invoices", AssignmentMasterViewSet, basename="invoice")
router.register("returns", ReturnRecordViewSet, basename="return")
router.register("reserve-alerts", ReserveAlertViewSet, basename="reserve-alert")
router.register("tracker-sessions", TrackerSessionViewSet, basename="tracker-session")
router.register("label-templates", LabelTemplateViewSet, basename="label-template")
router.register("label-print-logs", LabelPrintLogViewSet, basename="label-print-log")

_schema_auth = {
    "authentication_classes": [ApiKeyAuthentication],
    "permission_classes": [IsAuthenticated],
}

urlpatterns = [
    path("auth/token/", ObtainEmployeeTokenView.as_view(), name="auth-token"),
    path("auth/token/revoke/", RevokeEmployeeTokenView.as_view(), name="auth-token-revoke"),
    path("returns/process/", ReturnProcessView.as_view(), name="return-process"),
    path("invoices/create/", InvoiceCreateView.as_view(), name="invoice-create"),
    path("invoices/<int:pk>/stamp/", InvoiceStampView.as_view(), name="invoice-stamp"),
    path("products/photos/", ProductPhotoUploadView.as_view(), name="product-photo-upload"),
    path(
        "products/<int:product_id>/images/",
        ProductImagesClearView.as_view(),
        name="product-images-clear",
    ),
    path(
        "products/<int:product_id>/images/<int:image_id>/",
        ProductImageDeleteView.as_view(),
        name="product-image-delete",
    ),
    path(
        "products/<int:product_id>/images/<int:image_id>/primary/",
        ProductImagePrimaryView.as_view(),
        name="product-image-primary",
    ),
    path("tracker/validate/", TrackerValidateView.as_view(), name="tracker-validate"),
    path(
        "tracker-sessions/opening/",
        TrackerOpeningCreateView.as_view(),
        name="tracker-opening-create",
    ),
    path(
        "label-print-logs/create/",
        LabelPrintLogCreateView.as_view(),
        name="label-print-log-create",
    ),
    path(
        "schema/",
        SpectacularAPIView.as_view(**_schema_auth),
        name="schema",
    ),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(
            url_name="api:schema",
            **_schema_auth,
        ),
        name="swagger-ui",
    ),
    path("", include(router.urls)),
]
