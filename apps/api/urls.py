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
