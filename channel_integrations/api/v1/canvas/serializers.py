"""
Serializers for Canvas.
"""

from rest_framework import serializers

from channel_integrations.api.serializers import (
    EnterpriseCustomerPluginConfigSerializer,
)
from channel_integrations.canvas.models import CanvasEnterpriseCustomerConfiguration


class CanvasEnterpriseCustomerConfigurationSerializer(
    EnterpriseCustomerPluginConfigSerializer
):
    class Meta:
        model = CanvasEnterpriseCustomerConfiguration
        extra_fields = (
            "client_id",
            "client_secret",
            "canvas_account_id",
            "canvas_base_url",
            "refresh_token",
            "uuid",
            "oauth_authorization_url",
        )
        fields = EnterpriseCustomerPluginConfigSerializer.Meta.fields + extra_fields

    client_id = serializers.CharField(
        required=False, allow_blank=False, read_only=False
    )
    client_secret = serializers.CharField(
        required=False, allow_blank=False, read_only=False
    )

    def _handle_credentials(self, instance, client_id=None, client_secret=None):
        """
        Helper to update credentials consistently (same pattern as Moodle).
        """
        if client_id and client_secret:
            instance.encrypted_client_id = client_id
            instance.encrypted_client_secret = client_secret

    def create(self, validated_data):
        client_id = validated_data.pop("client_id", None)
        client_secret = validated_data.pop("client_secret", None)

        instance = super().create(validated_data)
        self._handle_credentials(instance, client_id, client_secret)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        client_id = validated_data.pop("client_id", None)
        client_secret = validated_data.pop("client_secret", None)

        instance = super().update(instance, validated_data)
        self._handle_credentials(instance, client_id, client_secret)
        instance.save()
        return instance
