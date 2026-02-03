"""
Serializer for Degreed2 configuration.
"""

from rest_framework import serializers

from channel_integrations.api.serializers import (
    EnterpriseCustomerPluginConfigSerializer,
)
from channel_integrations.degreed2.models import Degreed2EnterpriseCustomerConfiguration


class Degreed2ConfigSerializer(EnterpriseCustomerPluginConfigSerializer):
    class Meta:
        model = Degreed2EnterpriseCustomerConfiguration
        extra_fields = (
            "client_id",
            "client_secret",
            "degreed_base_url",
            "degreed_token_fetch_base_url",
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
        Helper to update credentials consistently.
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
