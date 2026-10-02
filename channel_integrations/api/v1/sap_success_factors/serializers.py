"""
Serializer for Success Factors configuration.
"""

from rest_framework import serializers

from channel_integrations.api.serializers import (
    EnterpriseCustomerPluginConfigSerializer,
)
from channel_integrations.sap_success_factors.models import SAPSuccessFactorsEnterpriseCustomerConfiguration
from channel_integrations.utils import MAX_PRIVATE_KEY_PEM_LENGTH


class SAPSuccessFactorsConfigSerializer(EnterpriseCustomerPluginConfigSerializer):
    class Meta:
        model = SAPSuccessFactorsEnterpriseCustomerConfiguration
        extra_fields = (
            "key",
            "sapsf_base_url",
            "sapsf_company_id",
            "sapsf_user_id",
            "secret",
            "auth_type",
            "private_key",
            "private_key_passphrase",
            "saml_assertion_audience",
            "user_type",
            "additional_locales",
            "show_course_price",
            "transmit_total_hours",
            "prevent_self_submit_grades",
        )
        fields = EnterpriseCustomerPluginConfigSerializer.Meta.fields + extra_fields

    key = serializers.CharField(required=False, allow_blank=False, read_only=False)
    secret = serializers.CharField(required=False, allow_blank=False, read_only=False)
    # allow_blank=True: omit to leave unchanged, submit "" to clear (matches MoodleConfigSerializer).
    private_key = serializers.CharField(
        required=False, allow_blank=True, write_only=True, max_length=MAX_PRIVATE_KEY_PEM_LENGTH
    )
    # trim_whitespace=False: decryption needs the exact passphrase bytes.
    private_key_passphrase = serializers.CharField(
        required=False, allow_blank=True, write_only=True, trim_whitespace=False,
        max_length=SAPSuccessFactorsEnterpriseCustomerConfiguration._meta.get_field(
            "decrypted_private_key_passphrase"
        ).max_length,
    )

    def validate(self, attrs):
        """Validates self-signed credentials against their effective post-save value."""
        attrs = super().validate(attrs)
        candidate = self.instance or SAPSuccessFactorsEnterpriseCustomerConfiguration()

        errors = candidate.get_credential_errors(
            auth_type=attrs.get("auth_type", candidate.auth_type),
            private_key=attrs.get("private_key", candidate.decrypted_private_key),
            private_key_passphrase=attrs.get("private_key_passphrase", candidate.decrypted_private_key_passphrase),
            saml_assertion_audience=attrs.get("saml_assertion_audience", candidate.saml_assertion_audience),
            sapsf_base_url=attrs.get("sapsf_base_url", candidate.sapsf_base_url),
        )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def _handle_credentials(self, instance, key=None, secret=None, private_key=None, private_key_passphrase=None):
        if key is not None:
            instance.encrypted_key = key
        if secret is not None:
            instance.encrypted_secret = secret
        if private_key is not None:
            instance.decrypted_private_key = private_key
        if private_key_passphrase is not None:
            instance.decrypted_private_key_passphrase = private_key_passphrase

    def create(self, validated_data):
        key = validated_data.pop("key", None)
        secret = validated_data.pop("secret", None)
        private_key = validated_data.pop("private_key", None)
        private_key_passphrase = validated_data.pop("private_key_passphrase", None)

        instance = super().create(validated_data)
        self._handle_credentials(instance, key, secret, private_key, private_key_passphrase)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        key = validated_data.pop("key", None)
        secret = validated_data.pop("secret", None)
        private_key = validated_data.pop("private_key", None)
        private_key_passphrase = validated_data.pop("private_key_passphrase", None)

        instance = super().update(instance, validated_data)
        self._handle_credentials(instance, key, secret, private_key, private_key_passphrase)
        instance.save()
        return instance
