from rest_framework import serializers

from apps.locations.models import Location


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = [
            "id",
            "name",
            "code",
            "location_type",
            "is_active",
            "created_at",
            "updated_at",
        ]
