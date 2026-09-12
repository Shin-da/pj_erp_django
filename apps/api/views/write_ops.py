import uuid

from django.db.models.functions import Lower
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.hardware.models import LabelPrintLog, LabelTemplate
from apps.inventory.models import ProductItem
from apps.locations.models import Location
from apps.tracker.models import ScanMode, ScanResult, TrackerScanItem, TrackerSession

from ..mixins import EmployeeWriteMixin
from ..serializers import LabelPrintLogSerializer, TrackerSessionSerializer


class TrackerValidateSerializer(serializers.Serializer):
    raw = serializers.CharField(allow_blank=True, default="")


class TrackerValidateView(EmployeeWriteMixin, APIView):
    """POST /api/v1/tracker/validate/ — normalize + existence check before submit."""

    required_permission = "tracker.add_trackersession"

    def post(self, request):
        ser = TrackerValidateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        raw = ser.validated_data.get("raw") or ""
        tokens = []
        seen = set()
        for part in raw.replace(",", "\n").splitlines():
            t = part.strip()
            if not t:
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            tokens.append(t)

        prefix_invalid = [t for t in tokens if not t.lower().startswith("pj")]
        candidates = [t for t in tokens if t.lower().startswith("pj")]
        existing = set(
            ProductItem.objects.annotate(barcode_lower=Lower("barcode"))
            .filter(barcode_lower__in=[c.lower() for c in candidates])
            .values_list("barcode_lower", flat=True)
        )
        valid = [c for c in candidates if c.lower() in existing]
        not_found = [c for c in candidates if c.lower() not in existing]
        return Response(
            {
                "normalized_text": "\n".join(valid),
                "removed_prefix": prefix_invalid,
                "removed_not_found": not_found,
            }
        )


class TrackerOpeningCreateSerializer(serializers.Serializer):
    location_code = serializers.CharField(max_length=20)
    barcodes = serializers.ListField(child=serializers.CharField(max_length=100), allow_empty=False)


class TrackerOpeningCreateView(EmployeeWriteMixin, APIView):
    """POST /api/v1/tracker-sessions/opening/ — create an OPENING balance scan."""

    required_permission = "tracker.add_trackersession"

    def post(self, request):
        ser = TrackerOpeningCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        location = Location.objects.filter(
            code__iexact=ser.validated_data["location_code"]
        ).first()
        if location is None:
            return Response({"detail": "Unknown location_code."}, status=status.HTTP_400_BAD_REQUEST)

        barcodes = ser.validated_data["barcodes"]
        items_by_key = {
            i.barcode.lower(): i
            for i in ProductItem.objects.filter(barcode__in=barcodes).select_related(
                "location", "product"
            )
        }
        at_location = []
        removed = []
        for bc in barcodes:
            item = items_by_key.get(bc.lower())
            if not item:
                removed.append({"barcode": bc, "reason": "Not found in the system"})
                continue
            if item.location_id != location.id:
                removed.append(
                    {
                        "barcode": bc,
                        "reason": f"System has it at {item.location.code}, not {location.code}",
                    }
                )
                continue
            at_location.append(item)

        status_map = {
            "PENDING": ScanResult.COMPANY_STOCK,
            "ASSIGNED": ScanResult.ASSIGNED,
            "SOLD": ScanResult.SOLD,
            "RESERVED": ScanResult.RESERVED,
        }
        session = TrackerSession.objects.create(
            mode=ScanMode.OPENING,
            location=location,
            created_by=request.user,
            item_count=len(at_location),
        )
        for item in at_location:
            result = status_map.get(item.status, ScanResult.OTHER)
            TrackerScanItem.objects.create(
                session=session,
                item=item,
                result=result,
                location_at_scan=location,
            )

        session = (
            TrackerSession.objects.select_related("location", "created_by")
            .prefetch_related("scan_items__item", "scan_items__location_at_scan")
            .get(pk=session.pk)
        )
        return Response(
            {
                "session": TrackerSessionSerializer(session, context={"request": request}).data,
                "removed": removed,
            },
            status=status.HTTP_201_CREATED,
        )


class LabelPrintLogCreateSerializer(serializers.Serializer):
    barcodes = serializers.ListField(child=serializers.CharField(max_length=100), allow_empty=False)
    status = serializers.ChoiceField(
        choices=[LabelPrintLog.Status.SUCCESS, LabelPrintLog.Status.ERROR],
        required=False,
        default=LabelPrintLog.Status.SUCCESS,
    )
    template_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    printer_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    error_message = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class LabelPrintLogCreateView(EmployeeWriteMixin, APIView):
    """POST /api/v1/label-print-logs/create/"""

    required_permission = "hardware.can_print_label"

    def post(self, request):
        ser = LabelPrintLogCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        barcodes = [b.strip() for b in data["barcodes"] if b.strip()][:500]
        if not barcodes:
            return Response({"detail": "no barcodes"}, status=status.HTTP_400_BAD_REQUEST)

        items_by_bc = {
            i.barcode.lower(): i
            for i in ProductItem.objects.filter(barcode__in=barcodes)
        }
        tpl = None
        if data.get("template_id"):
            tpl = LabelTemplate.objects.filter(pk=data["template_id"]).first()

        batch_id = uuid.uuid4()
        rows = []
        for barcode in barcodes:
            item = items_by_bc.get(barcode.lower())
            rows.append(
                LabelPrintLog(
                    batch_id=batch_id,
                    barcode=item.barcode if item else barcode[:100],
                    item=item,
                    template=tpl,
                    template_name=(tpl.name if tpl else "")[:100],
                    printed_by=request.user,
                    printer_name=data.get("printer_name") or "",
                    quantity=1,
                    status=data["status"],
                    error_message=(
                        data.get("error_message") or ""
                        if data["status"] == LabelPrintLog.Status.ERROR
                        else ""
                    ),
                )
            )
        LabelPrintLog.objects.bulk_create(rows)
        created = LabelPrintLog.objects.filter(batch_id=batch_id).select_related(
            "printed_by", "template"
        )
        return Response(
            {
                "batch_id": str(batch_id),
                "logged": len(rows),
                "results": LabelPrintLogSerializer(created, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )
