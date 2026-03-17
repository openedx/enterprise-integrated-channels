import pytest

from channel_integrations.api.v1.canvas.serializers import (
    CanvasEnterpriseCustomerConfigurationSerializer,
)
from test_utils.factories import (
    CanvasEnterpriseCustomerConfigurationFactory,
    EnterpriseCustomerFactory,
)


@pytest.mark.django_db
class TestCanvasConfigSerializer:

    def test_create_with_plain_credentials(self):
        enterprise_customer = EnterpriseCustomerFactory()
        data = {
            "enterprise_customer": enterprise_customer.uuid,
            "active": True,
            "canvas_base_url": "https://canvas.test.com",
            "canvas_account_id": "123",
            "client_id": "plain-client-id",
            "client_secret": "plain-client-secret",
        }

        serializer = CanvasEnterpriseCustomerConfigurationSerializer(data=data)
        assert serializer.is_valid(), serializer.errors  # pylint: disable=not-callable

        instance = serializer.save()

        # Plain credentials should be encrypted & stored
        assert instance.decrypted_client_id == "plain-client-id"
        assert instance.decrypted_client_secret == "plain-client-secret"

        # No refresh token or mixed credentials
        assert instance.refresh_token is None or instance.refresh_token == ""

    def test_update_with_new_plain_credentials(self):
        instance = CanvasEnterpriseCustomerConfigurationFactory(
            canvas_base_url="https://canvas.test.com",
            canvas_account_id="123",
            decrypted_client_id="old-id",
            decrypted_client_secret="old-secret",
        )

        data = {
            "client_id": "new-client-id",
            "client_secret": "new-client-secret",
        }

        serializer = CanvasEnterpriseCustomerConfigurationSerializer(
            instance, data=data, partial=True
        )
        assert serializer.is_valid(), serializer.errors  # pylint: disable=not-callable

        instance = serializer.save()

        # Old values replaced
        assert instance.decrypted_client_id == "new-client-id"
        assert instance.decrypted_client_secret == "new-client-secret"
