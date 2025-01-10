from rest_framework_mongoengine.serializers import DocumentSerializer
from rest_framework import serializers
from ms_load_from_senitron.models import (
    SenitronItemAsset,
    SenitronStatus,
    SenitronItem
)

class SenitronStatusSerializer(DocumentSerializer):
    class Meta:
        model = SenitronStatus
        fields = "__all__"

class SenitronItemSerializer(DocumentSerializer):
    class Meta:
        model = SenitronItem
        fields = "__all__"

class SenitronItemAssetSerializer(DocumentSerializer):
    # status = SenitronStatusSerializer()
    status = serializers.CharField(source='status.name')
    senitron_item = SenitronItemSerializer()

    class Meta:
        model = SenitronItemAsset
        fields = "__all__"