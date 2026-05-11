"""
Tests for the Moodle admin module.
"""

from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponseRedirect
from django.test import TestCase
from pytest import mark

from channel_integrations.moodle.admin import (
    MoodleEnterpriseCustomerConfigurationAdmin,
    MoodleLearnerDataTransmissionAuditAdmin,
)
from channel_integrations.moodle.models import (
    MoodleEnterpriseCustomerConfiguration,
    MoodleLearnerDataTransmissionAudit,
)
from test_utils import factories


@mark.django_db
class TestMoodleEnterpriseCustomerConfigurationAdmin(TestCase):
    """
    Tests for the ``MoodleEnterpriseCustomerConfigurationAdmin`` admin class.
    """

    def setUp(self):
        """
        Set up test data.
        """
        super().setUp()
        self.admin_site = AdminSite()
        self.admin_instance = MoodleEnterpriseCustomerConfigurationAdmin(
            MoodleEnterpriseCustomerConfiguration, self.admin_site
        )
        self.audit_admin_instance = MoodleLearnerDataTransmissionAuditAdmin(
            MoodleLearnerDataTransmissionAudit, self.admin_site
        )
        self.moodle_config = factories.MoodleEnterpriseCustomerConfigurationFactory()
        self.request = HttpRequest()
        self.request.session = {}
        self.request._messages = MagicMock()  # pylint:disable=protected-access

    def test_force_content_metadata_transmission_success(self):
        """
        Test force_content_metadata_transmission method with successful save.
        """
        with patch.object(self.moodle_config.enterprise_customer, 'save') as mock_save:
            response = self.admin_instance.force_content_metadata_transmission(
                self.request, self.moodle_config
            )

            # Verify the enterprise customer save was called
            mock_save.assert_called_once()

            # Verify the response is a redirect to the correct URL
            assert isinstance(response, HttpResponseRedirect)
            assert response.url == "/admin/moodle_channel/moodleenterprisecustomerconfiguration"

    def test_force_content_metadata_transmission_validation_error(self):
        """
        Test force_content_metadata_transmission method with ValidationError.
        """
        with patch.object(
            self.moodle_config.enterprise_customer, 'save',
            side_effect=ValidationError("Test validation error")
        ) as mock_save:
            response = self.admin_instance.force_content_metadata_transmission(
                self.request, self.moodle_config
            )

            # Verify the enterprise customer save was called
            mock_save.assert_called_once()

            # Verify the response is a redirect to the correct URL
            assert isinstance(response, HttpResponseRedirect)
            assert response.url == "/admin/moodle_channel/moodleenterprisecustomerconfiguration"

    def test_force_content_metadata_transmission_label(self):
        """
        Test that the force_content_metadata_transmission method has the correct label.
        """
        assert self.admin_instance.force_content_metadata_transmission.label == "Force content metadata transmission"

    def test_moodle_audit_admin_exposes_diagnostic_fields(self):
        """
        Test the admin exposes the extra detail fields needed for local inspection.
        """
        assert self.audit_admin_instance.list_display == (
            "enterprise_course_enrollment_id",
            "course_id",
            "status",
            "api_response_status_code",
            "progress_status",
            "modified",
        )
        assert self.audit_admin_instance.fields == (
            "enterprise_customer_name",
            "enterprise_course_enrollment_id",
            "user_email",
            "moodle_user_email",
            "course_id",
            "content_title",
            "progress_status",
            "grade",
            "status",
            "is_transmitted",
            "friendly_status_message",
            "formatted_error_message",
            "api_response_status_code",
            "api_response_body",
            "api_record",
        )
        assert "error_message" in self.audit_admin_instance.search_fields

    def test_api_response_status_code(self):
        """
        Test rendering of the API response status helper.
        """
        obj = MagicMock()
        obj.api_record = MagicMock(status_code=404)

        assert self.audit_admin_instance.api_response_status_code(obj) == 404

    def test_formatted_error_message(self):
        """
        Test rendering of the error message helper.
        """
        obj = MagicMock()
        obj.error_message = "Completion course module not found"

        assert "Completion course module not found" in str(self.audit_admin_instance.formatted_error_message(obj))

    def test_api_response_body(self):
        """
        Test rendering of the API response body helper.
        """
        obj = MagicMock()
        obj.api_record = MagicMock(body='MoodleAPIClient request failed: 404 Completion course module not found')

        assert "Completion course module not found" in str(self.audit_admin_instance.api_response_body(obj))
