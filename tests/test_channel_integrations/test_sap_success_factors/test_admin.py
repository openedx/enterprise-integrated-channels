"""
Tests for the SAP Success Factors admin module.
"""

import datetime
from unittest.mock import MagicMock, patch

import ddt
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponseRedirect
from django.test import TestCase
from pytest import mark
from requests import RequestException

from channel_integrations.exceptions import ClientError
from channel_integrations.sap_success_factors.admin import SAPSuccessFactorsEnterpriseCustomerConfigurationAdmin
from channel_integrations.sap_success_factors.client import SAPSuccessFactorsAPIClient
from channel_integrations.sap_success_factors.models import (
    SAPAuthType,
    SAPSuccessFactorsEnterpriseCustomerConfiguration,
)
from test_utils import factories


@ddt.ddt
@mark.django_db
class TestSAPSuccessFactorsEnterpriseCustomerConfigurationAdmin(TestCase):
    """
    Tests for the ``SAPSuccessFactorsEnterpriseCustomerConfigurationAdmin`` admin class.
    """

    def setUp(self):
        """
        Set up test data.
        """
        super().setUp()
        self.admin_site = AdminSite()
        self.admin_instance = SAPSuccessFactorsEnterpriseCustomerConfigurationAdmin(
            SAPSuccessFactorsEnterpriseCustomerConfiguration, self.admin_site
        )
        self.sap_config = factories.SAPSuccessFactorsEnterpriseCustomerConfigurationFactory()
        self.request = HttpRequest()
        self.request.session = {}
        self.request._messages = MagicMock()  # pylint:disable=protected-access

    def test_force_content_metadata_transmission_success(self):
        """
        Test force_content_metadata_transmission method with successful save.
        """
        with patch.object(self.sap_config.enterprise_customer, 'save') as mock_save:
            response = self.admin_instance.force_content_metadata_transmission(
                self.request, self.sap_config
            )

            # Verify the enterprise customer save was called
            mock_save.assert_called_once()

            # Verify the response is a redirect to the correct URL
            assert isinstance(response, HttpResponseRedirect)
            assert response.url == "/admin/sap_success_factors_channel/sapsuccessfactorsenterprisecustomerconfiguration"

    def test_force_content_metadata_transmission_validation_error(self):
        """
        Test force_content_metadata_transmission method with ValidationError.
        """
        with patch.object(
            self.sap_config.enterprise_customer, 'save',
            side_effect=ValidationError("Test validation error")
        ) as mock_save:
            response = self.admin_instance.force_content_metadata_transmission(
                self.request, self.sap_config
            )

            # Verify the enterprise customer save was called
            mock_save.assert_called_once()

            # Verify the response is a redirect to the correct URL
            assert isinstance(response, HttpResponseRedirect)
            assert response.url == "/admin/sap_success_factors_channel/sapsuccessfactorsenterprisecustomerconfiguration"

    def test_force_content_metadata_transmission_label(self):
        """
        Test that the force_content_metadata_transmission method has the correct label.
        """
        assert self.admin_instance.force_content_metadata_transmission.label == "Force content metadata transmission"

    def test_has_access_token_success(self):
        """
        Returns True when the client returns a token.
        """
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        with patch(
            "channel_integrations.sap_success_factors.admin.SAPSuccessFactorsAPIClient"
        ) as mock_client_class:
            mock_client_class.return_value.get_access_token.return_value = ("a-token", expires_at)
            result = self.admin_instance.has_access_token(self.sap_config)

        assert result is True
        mock_client_class.assert_called_once_with(self.sap_config)
        mock_client_class.return_value.get_access_token.assert_called_once_with(
            self.sap_config.sapsf_user_id,
            self.sap_config.user_type,
            timeout=mock_client_class.return_value.SESSION_TIMEOUT,
        )

    def test_has_access_token_request_exception_returns_false(self):
        """
        Returns False, instead of raising, when token acquisition raises a RequestException.
        """
        with patch(
            "channel_integrations.sap_success_factors.admin.SAPSuccessFactorsAPIClient"
        ) as mock_client_class:
            mock_client_class.return_value.get_access_token.side_effect = RequestException("boom")
            result = self.admin_instance.has_access_token(self.sap_config)

        assert result is False

    def test_has_access_token_client_error_returns_false(self):
        """
        Returns False, instead of raising, when token acquisition raises a ClientError.
        """
        with patch(
            "channel_integrations.sap_success_factors.admin.SAPSuccessFactorsAPIClient"
        ) as mock_client_class:
            mock_client_class.return_value.get_access_token.side_effect = ClientError("bad response", 500)
            result = self.admin_instance.has_access_token(self.sap_config)

        assert result is False

    @ddt.data(SAPAuthType.SAP_SIGNED_ASSERTION, SAPAuthType.SELF_SIGNED_ASSERTION)
    def test_has_access_token_does_not_raise_attribute_error(self, auth_type):
        """
        Regression test: exercises the real client (only the network call, and for self-signed the
        assertion signing, are mocked) for both auth types, to confirm has_access_token no longer
        raises AttributeError and that the configured timeout reaches the HTTP call.
        """
        self.sap_config.auth_type = auth_type
        with patch("channel_integrations.sap_success_factors.client.requests.post") as mock_post, patch(
            "channel_integrations.sap_success_factors.client.generate_saml_assertion", return_value="<assertion/>"
        ):
            mock_post.side_effect = RequestException("network unreachable")
            result = self.admin_instance.has_access_token(self.sap_config)

        assert result is False
        assert mock_post.call_args.kwargs['timeout'] == SAPSuccessFactorsAPIClient.SESSION_TIMEOUT

    def test_has_access_token_returns_none_for_unsaved_config(self):
        """
        Regression test: returns None, without making a request, for an unsaved config (e.g. the
        admin Add form) -- it has no pk yet for the request to be logged against.
        """
        unsaved_config = factories.SAPSuccessFactorsEnterpriseCustomerConfigurationFactory.build()
        with patch("channel_integrations.sap_success_factors.client.requests.post") as mock_post:
            result = self.admin_instance.has_access_token(unsaved_config)

        assert result is None
        mock_post.assert_not_called()
