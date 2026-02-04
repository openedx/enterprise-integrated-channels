"""
Serializer for Success Factors configuration.
"""

from rest_framework import serializers

from channel_integrations.api.serializers import (
    EnterpriseCustomerPluginConfigSerializer,
)
from channel_integrations.sap_success_factors.models import (
    SAPSuccessFactorsEnterpriseCustomerConfiguration,
)


class SAPSuccessFactorsConfigSerializer(EnterpriseCustomerPluginConfigSerializer):
    class Meta:
        model = SAPSuccessFactorsEnterpriseCustomerConfiguration
        extra_fields = (
            "key",
            "sapsf_base_url",
            "sapsf_company_id",
            "sapsf_user_id",
            "secret",
            "user_type",
            "additional_locales",
            "show_course_price",
            "transmit_total_hours",
            "prevent_self_submit_grades",
        )
        fields = EnterpriseCustomerPluginConfigSerializer.Meta.fields + extra_fields

    key = serializers.CharField(required=False, allow_blank=False, read_only=False)
    secret = serializers.CharField(required=False, allow_blank=False, read_only=False)

    def _handle_credentials(self, instance, key=None, secret=None):
        """
        Helper to update credentials consistently.
        """
        if key and secret:
            instance.encrypted_key = key
            instance.encrypted_secret = secret

    def create(self, validated_data):
        key = validated_data.pop("key", None)
        secret = validated_data.pop("secret", None)

        instance = super().create(validated_data)
        self._handle_credentials(instance, key, secret)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        key = validated_data.pop("key", None)
        secret = validated_data.pop("secret", None)

        instance = super().update(instance, validated_data)
        self._handle_credentials(instance, key, secret)
        instance.save()
        return instance
