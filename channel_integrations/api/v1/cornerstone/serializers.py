"""
    Serializer for Cornerstone configuration.
"""
from rest_framework import serializers

from channel_integrations.api.serializers import EnterpriseCustomerPluginConfigSerializer
from channel_integrations.cornerstone.models import CornerstoneEnterpriseCustomerConfiguration


class CornerstoneConfigSerializer(EnterpriseCustomerPluginConfigSerializer):
    class Meta:
        model = CornerstoneEnterpriseCustomerConfiguration
        extra_fields = (
            'cornerstone_base_url',
            'client_id',
            'client_secret',
            'session_token',
            'session_token_modified'
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
        if client_id is not None:
            instance.encrypted_client_id = client_id
        if client_secret is not None:
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
