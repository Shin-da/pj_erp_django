from rest_framework import serializers


class EmployeeMiniSerializer(serializers.Serializer):
    """Safe staff stub for created_by / processed_by / printed_by embeds."""

    id = serializers.IntegerField()
    employee_code = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
