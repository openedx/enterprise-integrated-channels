"""
Tests for the xAPI admin module.
"""

from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponseRedirect
from django.test import TestCase
from pytest import mark

from channel_integrations.xapi.admin import XAPILRSConfigurationAdmin
from channel_integrations.xapi.models import XAPILRSConfiguration
from test_utils import factories


@mark.django_db
class TestXAPILRSConfigurationAdmin(TestCase):
    """
    Tests for the ``XAPILRSConfigurationAdmin`` admin class.
    """

    def setUp(self):
        """
        Set up test data.
        """
        super().setUp()
        self.admin_site = AdminSite()
        self.admin_instance = XAPILRSConfigurationAdmin(XAPILRSConfiguration, self.admin_site)
        self.x_api_lrs_config = factories.XAPILRSConfigurationFactory()
        self.request = HttpRequest()
        self.request.session = {}
        self.request._messages = MagicMock()  # pylint:disable=protected-access

    def test_enterprise_customer_name(self):
        """
        Test the enterprise_customer_name method returns the correct name.
        """
        result = self.admin_instance.enterprise_customer_name(self.x_api_lrs_config)
        assert result == self.x_api_lrs_config.enterprise_customer.name

    def test_force_content_metadata_transmission_success(self):
        """
        Test force_content_metadata_transmission method with successful save.
        """
        with patch.object(self.x_api_lrs_config.enterprise_customer, 'save') as mock_save:
            response = self.admin_instance.force_content_metadata_transmission(
                self.request, self.x_api_lrs_config
            )

            # Verify the enterprise customer save was called
            mock_save.assert_called_once()

            # Verify the response is a redirect to the correct URL
            assert isinstance(response, HttpResponseRedirect)
            assert response.url == "/admin/xapi_channel/xapilrsconfiguration/"

    def test_force_content_metadata_transmission_validation_error(self):
        """
        Test force_content_metadata_transmission method with ValidationError.
        """
        with patch.object(
            self.x_api_lrs_config.enterprise_customer, 'save',
            side_effect=ValidationError("Test validation error")
        ) as mock_save:
            response = self.admin_instance.force_content_metadata_transmission(
                self.request, self.x_api_lrs_config
            )

            # Verify the enterprise customer save was called
            mock_save.assert_called_once()

            # Verify the response is a redirect to the correct URL
            assert isinstance(response, HttpResponseRedirect)
            assert response.url == "/admin/xapi_channel/xapilrsconfiguration/"

    def test_force_content_metadata_transmission_label(self):
        """
        Test that the force_content_metadata_transmission method has the correct label.
        """
        assert self.admin_instance.force_content_metadata_transmission.label == "Force content metadata transmission"
