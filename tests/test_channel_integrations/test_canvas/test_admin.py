"""
Tests for the Canvas admin module.
"""

from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponseRedirect
from django.test import TestCase
from pytest import mark

from channel_integrations.canvas.admin import CanvasEnterpriseCustomerConfigurationAdmin
from channel_integrations.canvas.models import CanvasEnterpriseCustomerConfiguration
from test_utils import factories


@mark.django_db
class TestCanvasEnterpriseCustomerConfigurationAdmin(TestCase):
    """
    Tests for the ``CanvasEnterpriseCustomerConfigurationAdmin`` admin class.
    """

    def setUp(self):
        """
        Set up test data.
        """
        super().setUp()
        self.admin_site = AdminSite()
        self.admin_instance = CanvasEnterpriseCustomerConfigurationAdmin(
            CanvasEnterpriseCustomerConfiguration, self.admin_site
        )
        self.canvas_config = factories.CanvasEnterpriseCustomerConfigurationFactory()
        self.request = HttpRequest()
        self.request.session = {}
        self.request._messages = MagicMock()  # pylint:disable=protected-access

    def test_enterprise_customer_name(self):
        """
        Test the enterprise_customer_name method returns the correct name.
        """
        result = self.admin_instance.enterprise_customer_name(self.canvas_config)
        assert result == self.canvas_config.enterprise_customer.name

    def test_customer_oauth_authorization_url_with_url(self):
        """
        Test customer_oauth_authorization_url when oauth_authorization_url is available.
        """
        with patch.object(
            type(self.canvas_config), 'oauth_authorization_url',
            new_callable=lambda: property(lambda self: 'https://example.com/auth')
        ):
            result = self.admin_instance.customer_oauth_authorization_url(self.canvas_config)
            assert 'href="https://example.com/auth"' in result
            assert 'Authorize Link' in result

    def test_customer_oauth_authorization_url_without_url(self):
        """
        Test customer_oauth_authorization_url when oauth_authorization_url is not available.
        """
        with patch.object(
            type(self.canvas_config), 'oauth_authorization_url',
            new_callable=lambda: property(lambda self: None)
        ):
            result = self.admin_instance.customer_oauth_authorization_url(self.canvas_config)
            assert result is None

    def test_force_content_metadata_transmission_success(self):
        """
        Test force_content_metadata_transmission method with successful save.
        """
        with patch.object(self.canvas_config.enterprise_customer, 'save') as mock_save:
            response = self.admin_instance.force_content_metadata_transmission(
                self.request, self.canvas_config
            )

            # Verify the enterprise customer save was called
            mock_save.assert_called_once()

            # Verify the response is a redirect to the correct URL
            assert isinstance(response, HttpResponseRedirect)
            assert response.url == "/admin/canvas_channel/canvasenterprisecustomerconfiguration"

    def test_force_content_metadata_transmission_validation_error(self):
        """
        Test force_content_metadata_transmission method with ValidationError.
        """
        with patch.object(
            self.canvas_config.enterprise_customer, 'save',
            side_effect=ValidationError("Test validation error")
        ) as mock_save:
            response = self.admin_instance.force_content_metadata_transmission(
                self.request, self.canvas_config
            )

            # Verify the enterprise customer save was called
            mock_save.assert_called_once()

            # Verify the response is a redirect to the correct URL
            assert isinstance(response, HttpResponseRedirect)
            assert response.url == "/admin/canvas_channel/canvasenterprisecustomerconfiguration"

    def test_force_content_metadata_transmission_label(self):
        """
        Test that the force_content_metadata_transmission method has the correct label.
        """
        assert self.admin_instance.force_content_metadata_transmission.label == "Force content metadata transmission"
