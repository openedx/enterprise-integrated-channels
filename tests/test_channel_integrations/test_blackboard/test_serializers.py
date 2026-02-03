import pytest

from channel_integrations.api.v1.blackboard.serializers import (
    BlackboardConfigSerializer,
)
from test_utils.factories import (
    BlackboardEnterpriseCustomerConfigurationFactory,
    EnterpriseCustomerFactory,
)


@pytest.mark.django_db
class TestBlackboardConfigSerializer:

    def test_create_with_plain_credentials_sets_encrypted_fields(self):
        enterprise_customer = EnterpriseCustomerFactory()
        data = {
            "enterprise_customer": enterprise_customer.uuid,
            "active": True,
            "blackboard_base_url": "https://bb.test.com",
            "client_id": "plain-client-id",
            "client_secret": "plain-client-secret",
        }

        serializer = BlackboardConfigSerializer(data=data)
        assert serializer.is_valid(), serializer.errors  # pylint: disable=not-callable

        instance = serializer.save()

        # This is the main behavior we fixed
        assert instance.decrypted_client_id == "plain-client-id"
        assert instance.decrypted_client_secret == "plain-client-secret"

    def test_update_with_new_credentials_updates_encrypted_fields(self):
        instance = BlackboardEnterpriseCustomerConfigurationFactory(
            blackboard_base_url="https://bb.test.com",
            decrypted_client_id="old-id",
            decrypted_client_secret="old-secret",
        )

        data = {
            "client_id": "new-client-id",
            "client_secret": "new-client-secret",
        }

        serializer = BlackboardConfigSerializer(instance, data=data, partial=True)
        assert serializer.is_valid(), serializer.errors  # pylint: disable=not-callable

        updated = serializer.save()

        assert updated.decrypted_client_id == "new-client-id"
        assert updated.decrypted_client_secret == "new-client-secret"

    def test_update_without_credentials_does_not_change_encrypted_fields(self):
        instance = BlackboardEnterpriseCustomerConfigurationFactory(
            blackboard_base_url="https://bb.test.com",
            decrypted_client_id="existing-id",
            decrypted_client_secret="existing-secret",
        )

        data = {
            "blackboard_base_url": "https://bb.changed.com",
        }

        serializer = BlackboardConfigSerializer(instance, data=data, partial=True)
        assert serializer.is_valid(), serializer.errors  # pylint: disable=not-callable

        updated = serializer.save()

        # Encrypted values must remain untouched
        assert updated.decrypted_client_id == "existing-id"
        assert updated.decrypted_client_secret == "existing-secret"
