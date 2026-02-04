import pytest

from channel_integrations.api.v1.degreed2.serializers import Degreed2ConfigSerializer
from test_utils.factories import (
    Degreed2EnterpriseCustomerConfigurationFactory,
    EnterpriseCustomerFactory,
)


@pytest.mark.django_db
class TestDegreed2ConfigSerializer:

    def test_create_with_client_id_secret_sets_encrypted_fields(self):
        enterprise_customer = EnterpriseCustomerFactory()
        data = {
            "enterprise_customer": enterprise_customer.uuid,
            "active": True,
            "degreed_base_url": "https://degreed.test.com",
            "degreed_token_fetch_base_url": "https://api.degreed.test.com",
            "client_id": "plain-client-id",
            "client_secret": "plain-client-secret",
        }

        serializer = Degreed2ConfigSerializer(data=data)
        assert serializer.is_valid(), serializer.errors  # pylint: disable=not-callable

        instance = serializer.save()

        # Main fix validation
        assert instance.decrypted_client_id == "plain-client-id"
        assert instance.decrypted_client_secret == "plain-client-secret"

    def test_update_with_new_client_credentials_updates_encrypted_fields(self):
        instance = Degreed2EnterpriseCustomerConfigurationFactory(
            degreed_base_url="https://degreed.test.com",
            degreed_token_fetch_base_url="https://api.degreed.test.com",
            decrypted_client_id="old-id",
            decrypted_client_secret="old-secret",
        )

        data = {
            "client_id": "new-client-id",
            "client_secret": "new-client-secret",
        }

        serializer = Degreed2ConfigSerializer(instance, data=data, partial=True)
        assert serializer.is_valid(), serializer.errors  # pylint: disable=not-callable

        updated = serializer.save()

        assert updated.decrypted_client_id == "new-client-id"
        assert updated.decrypted_client_secret == "new-client-secret"

    def test_update_without_credentials_does_not_change_encrypted_fields(self):
        instance = Degreed2EnterpriseCustomerConfigurationFactory(
            degreed_base_url="https://degreed.test.com",
            degreed_token_fetch_base_url="https://api.degreed.test.com",
            decrypted_client_id="existing-id",
            decrypted_client_secret="existing-secret",
        )

        data = {
            "degreed_base_url": "https://changed.degreed.test.com",
        }

        serializer = Degreed2ConfigSerializer(instance, data=data, partial=True)
        assert serializer.is_valid(), serializer.errors  # pylint: disable=not-callable

        updated = serializer.save()

        # Credentials must remain unchanged
        assert updated.decrypted_client_id == "existing-id"
        assert updated.decrypted_client_secret == "existing-secret"
