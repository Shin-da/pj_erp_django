from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.inventory.models import InvalidStatusTransition
from apps.returns.services import OFFERED_OUTCOMES, process_return_batch

from ..mixins import EmployeeWriteMixin
from ..serializers import ReturnRecordSerializer


class ReturnProcessItemSerializer(serializers.Serializer):
    barcode = serializers.CharField(max_length=100)
    outcome = serializers.ChoiceField(choices=[v for v, _ in OFFERED_OUTCOMES])


class ReturnProcessSerializer(serializers.Serializer):
    items = ReturnProcessItemSerializer(many=True)


class ReturnProcessView(EmployeeWriteMixin, APIView):
    """POST /api/v1/returns/process/ — batch return / sold / reserve."""

    required_permission = "returns.can_process_return"

    def post(self, request):
        ser = ReturnProcessSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pairs = [(row["barcode"], row["outcome"]) for row in ser.validated_data["items"]]
        try:
            records = process_return_batch(pairs=pairs, actor=request.user)
        except (DjangoValidationError, InvalidStatusTransition) as exc:
            detail = (
                exc.messages[0]
                if isinstance(exc, DjangoValidationError) and getattr(exc, "messages", None)
                else str(exc)
            )
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        out = ReturnRecordSerializer(records, many=True, context={"request": request})
        return Response(
            {"processed": len(records), "results": out.data},
            status=status.HTTP_201_CREATED,
        )
