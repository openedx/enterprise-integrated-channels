import pytest

from channel_integrations.api.v1.sap_success_factors.serializers import (
    SAPSuccessFactorsConfigSerializer,
)
from test_utils.factories import (
    SAPSuccessFactorsEnterpriseCustomerConfigurationFactory,
    EnterpriseCustomerFactory,
)


@pytest.mark.django_db
class TestSAPSuccessFactorsConfigSerializer:

    def test_create_with_key_secret_sets_encrypted_fields(self):
        enterprise_customer = EnterpriseCustomerFactory()
        data = {
            "enterprise_customer": enterprise_customer.uuid,
            "active": True,
            "sapsf_base_url": "https://sap.test.com",
            "sapsf_company_id": "COMP1",
            "key": "plain-key",
            "secret": "plain-secret",
        }

        serializer = SAPSuccessFactorsConfigSerializer(data=data)
        assert serializer.is_valid(), serializer.errors  # pylint: disable=not-callable

        instance = serializer.save()

        # Main fix validation
        assert instance.decrypted_key == "plain-key"
        assert instance.decrypted_secret == "plain-secret"

    def test_update_with_new_key_secret_updates_encrypted_fields(self):
        instance = SAPSuccessFactorsEnterpriseCustomerConfigurationFactory(
            sapsf_base_url="https://sap.test.com",
            sapsf_company_id="COMP1",
            decrypted_key="old-key",
            decrypted_secret="old-secret",
        )

        data = {
            "key": "new-key",
            "secret": "new-secret",
        }

        serializer = SAPSuccessFactorsConfigSerializer(
            instance, data=data, partial=True
        )
        assert serializer.is_valid(), serializer.errors  # pylint: disable=not-callable

        updated = serializer.save()

        assert updated.decrypted_key == "new-key"
        assert updated.decrypted_secret == "new-secret"

    def test_update_without_credentials_does_not_change_encrypted_fields(self):
        instance = SAPSuccessFactorsEnterpriseCustomerConfigurationFactory(
            sapsf_base_url="https://sap.test.com",
            sapsf_company_id="COMP1",
            decrypted_key="existing-key",
            decrypted_secret="existing-secret",
        )

        data = {
            "sapsf_company_id": "COMP2",
        }

        serializer = SAPSuccessFactorsConfigSerializer(
            instance, data=data, partial=True
        )
        assert serializer.is_valid(), serializer.errors  # pylint: disable=not-callable

        updated = serializer.save()

        # Credentials must remain unchanged
        assert updated.decrypted_key == "existing-key"
        assert updated.decrypted_secret == "existing-secret"
