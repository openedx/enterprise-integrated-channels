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

    @ddt.data(SAPAuthType.SAP_SIGNED_ASSERTION, SAPAuthType.SELF_SIGNED_ASSERTION)
    def test_has_access_token_success(self, auth_type):
        """
        has_access_token requests a token through a client for the config and reports True when one
        is returned. Self-signed configs are checked the same way, since the client requests every
        config's access token with the OAuth client id and secret.
        """
        self.sap_config.auth_type = auth_type
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        with patch(
            "channel_integrations.sap_success_factors.admin.SAPSuccessFactorsAPIClient"
        ) as mock_client_class:
            mock_client_class.return_value.get_oauth_access_token.return_value = ("a-token", expires_at)
            result = self.admin_instance.has_access_token(self.sap_config)

        assert result is True
        mock_client_class.assert_called_once_with(self.sap_config)
        mock_client_class.return_value.get_oauth_access_token.assert_called_once_with(
            self.sap_config.decrypted_key,
            self.sap_config.decrypted_secret,
            self.sap_config.sapsf_company_id,
            self.sap_config.sapsf_user_id,
            self.sap_config.user_type,
            self.sap_config.enterprise_customer.uuid,
        )

    def test_has_access_token_request_exception_returns_false(self):
        """
        A RequestException from token acquisition is caught and reported as no access token,
        rather than propagating out of the admin form.
        """
        with patch(
            "channel_integrations.sap_success_factors.admin.SAPSuccessFactorsAPIClient"
        ) as mock_client_class:
            mock_client_class.return_value.get_oauth_access_token.side_effect = RequestException("boom")
            result = self.admin_instance.has_access_token(self.sap_config)

        assert result is False

    def test_has_access_token_client_error_returns_false(self):
        """
        A ClientError from token acquisition (e.g. an unparseable SAP response) is caught and
        reported as no access token, rather than propagating out of the admin form.
        """
        with patch(
            "channel_integrations.sap_success_factors.admin.SAPSuccessFactorsAPIClient"
        ) as mock_client_class:
            mock_client_class.return_value.get_oauth_access_token.side_effect = ClientError("bad response", 500)
            result = self.admin_instance.has_access_token(self.sap_config)

        assert result is False

    def test_has_access_token_does_not_raise_attribute_error(self):
        """
        Regression test for the original defect: has_access_token used to call
        get_oauth_access_token unbound on the class, which raised an uncaught AttributeError
        (obj.sapsf_base_url doesn't have `.enterprise_configuration`) as soon as an admin
        opened a SAP customer configuration change form. Exercise the real client wiring
        (only the outbound network call is mocked) to confirm that no longer happens.
        """
        with patch("channel_integrations.sap_success_factors.client.requests.post") as mock_post:
            mock_post.side_effect = RequestException("network unreachable")
            result = self.admin_instance.has_access_token(self.sap_config)

        assert result is False
