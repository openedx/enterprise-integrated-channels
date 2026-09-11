"""
Tests for the Cornerstone admin module.
"""

from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponseRedirect
from django.test import TestCase
from pytest import mark

from channel_integrations.cornerstone.admin import (
    CornerstoneEnterpriseCustomerConfigurationAdmin,
    CornerstoneLearnerDataTransmissionAuditAdmin,
)
from channel_integrations.cornerstone.models import (
    CornerstoneEnterpriseCustomerConfiguration,
    CornerstoneLearnerDataTransmissionAudit,
)
from test_utils import factories


@mark.django_db
class TestCornerstoneEnterpriseCustomerConfigurationAdmin(TestCase):
    """
    Tests for the ``CornerstoneEnterpriseCustomerConfigurationAdmin`` admin class.
    """

    def setUp(self):
        """
        Set up test data.
        """
        super().setUp()
        self.admin_site = AdminSite()
        self.admin_instance = CornerstoneEnterpriseCustomerConfigurationAdmin(
            CornerstoneEnterpriseCustomerConfiguration, self.admin_site
        )
        self.cornerstone_config = factories.CornerstoneEnterpriseCustomerConfigurationFactory()
        self.request = HttpRequest()
        self.request.session = {}
        self.request._messages = MagicMock()  # pylint:disable=protected-access

    def test_force_content_metadata_transmission_success(self):
        """
        Test force_content_metadata_transmission method with successful save.
        """
        with patch.object(self.cornerstone_config.enterprise_customer, 'save') as mock_save:
            response = self.admin_instance.force_content_metadata_transmission(
                self.request, self.cornerstone_config
            )

            # Verify the enterprise customer save was called
            mock_save.assert_called_once()

            # Verify the response is a redirect to the correct URL
            assert isinstance(response, HttpResponseRedirect)
            assert response.url == "/admin/cornerstone_channel/cornerstoneenterprisecustomerconfiguration"

    def test_force_content_metadata_transmission_validation_error(self):
        """
        Test force_content_metadata_transmission method with ValidationError.
        """
        with patch.object(
            self.cornerstone_config.enterprise_customer, 'save',
            side_effect=ValidationError("Test validation error")
        ) as mock_save:
            response = self.admin_instance.force_content_metadata_transmission(
                self.request, self.cornerstone_config
            )

            # Verify the enterprise customer save was called
            mock_save.assert_called_once()

            # Verify the response is a redirect to the correct URL
            assert isinstance(response, HttpResponseRedirect)
            assert response.url == "/admin/cornerstone_channel/cornerstoneenterprisecustomerconfiguration"

    def test_force_content_metadata_transmission_label(self):
        """
        Test that the force_content_metadata_transmission method has the correct label.
        """
        assert self.admin_instance.force_content_metadata_transmission.label == "Force content metadata transmission"

    def test_enterprise_customer_name(self):
        """
        Test the enterprise_customer_name method returns the associated enterprise customer's name.
        """
        assert self.admin_instance.enterprise_customer_name(
            self.cornerstone_config
        ) == self.cornerstone_config.enterprise_customer.name

    def test_oauth_configured_false_by_default(self):
        """
        Test that oauth_configured is False when no OAuth credentials are set.
        """
        assert self.admin_instance.oauth_configured(self.cornerstone_config) is False

    def test_oauth_configured_true_when_credentials_set(self):
        """
        Test that oauth_configured is True when both client id and secret are set.
        """
        self.cornerstone_config.decrypted_client_id = 'my-client-id'
        self.cornerstone_config.decrypted_client_secret = 'my-client-secret'
        self.cornerstone_config.save()
        assert self.admin_instance.oauth_configured(self.cornerstone_config) is True


@mark.django_db
class TestCornerstoneLearnerDataTransmissionAuditAdmin(TestCase):
    """
    Tests for the ``CornerstoneLearnerDataTransmissionAuditAdmin`` admin class.
    """

    def setUp(self):
        """
        Set up test data.
        """
        super().setUp()
        self.admin_site = AdminSite()
        self.admin_instance = CornerstoneLearnerDataTransmissionAuditAdmin(
            CornerstoneLearnerDataTransmissionAudit, self.admin_site
        )
        self.user = factories.UserFactory()
        self.audit = factories.CornerstoneLearnerDataTransmissionAuditFactory(user=self.user)

    def test_user_email(self):
        """
        Test the user_email method returns the associated user's email.
        """
        assert self.admin_instance.user_email(self.audit) == self.user.email
