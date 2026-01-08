"""
Integration tests for Webhook event handlers.
"""
import logging
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from opaque_keys.edx.keys import CourseKey
from openedx_events.learning.data import (
    CourseData,
    CourseEnrollmentData,
    PersistentCourseGradeData,
    UserData,
    UserPersonalData,
)

from channel_integrations.integrated_channel.handlers import (
    handle_enrollment_for_webhooks,
    handle_grade_change_for_webhooks,
)
from channel_integrations.integrated_channel.services.webhook_routing import NoWebhookConfigured
from test_utils.factories import EnterpriseCustomerFactory, EnterpriseCustomerUserFactory

User = get_user_model()


@pytest.mark.django_db
class TestWebhookHandlers:
    """Tests for handlers.py."""

    def test_handle_grade_change_success(self):
        """Verify that a passing grade event queues a completion webhook."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_key = CourseKey.from_string('course-v1:edX+DemoX+Demo_Course')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Demo Course'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.85,
            letter_grade='B',
            passed_timestamp=timezone.now()
        )

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region') as mock_route:
            handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

            mock_route.assert_called_once()
            _, kwargs = mock_route.call_args
            assert kwargs['user'] == user
            assert kwargs['enterprise_customer'] == enterprise
            assert kwargs['event_type'] == 'course_completion'
            assert kwargs['payload']['completion']['percent_grade'] == 0.85

    def test_handle_grade_change_non_passing(self):
        """Verify that a non-passing grade event is ignored."""
        user = User.objects.create(username='testuser')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=CourseKey.from_string('course-v1:edX+DemoX+Demo_Course'), display_name='Demo'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.4,
            letter_grade='F',
            passed_timestamp=None
        )

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region') as mock_route:
            handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)
            mock_route.assert_not_called()

    def test_handle_enrollment_success(self):
        """Verify that an enrollment event queues an enrollment webhook."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_key = CourseKey.from_string('course-v1:edX+DemoX+Demo_Course')

        enrollment_data = CourseEnrollmentData(
            user=UserData(id=user.id, is_active=True, pii=UserPersonalData(username=user.username, email=user.email)),
            course=CourseData(course_key=course_key, display_name='Demo Course'),
            mode='verified',
            is_active=True,
            creation_date=timezone.now()
        )

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region') as mock_route:
            handle_enrollment_for_webhooks(sender=None, signal=None, enrollment=enrollment_data)

            mock_route.assert_called_once()
            _, kwargs = mock_route.call_args
            assert kwargs['user'] == user
            assert kwargs['event_type'] == 'course_enrollment'
            assert kwargs['payload']['enrollment']['mode'] == 'verified'

    def test_handle_enrollment_non_enterprise(self):
        """Verify that events for non-enterprise users are ignored."""
        user = User.objects.create(username='testuser', email='test@example.com')
        # No EnterpriseCustomerUser record

        enrollment_data = CourseEnrollmentData(
            user=UserData(id=user.id, is_active=True, pii=UserPersonalData(username=user.username, email=user.email)),
            course=CourseData(course_key=CourseKey.from_string('course-v1:edX+DemoX+Demo_Course'), display_name='Demo'),
            mode='audit',
            is_active=True,
            creation_date=timezone.now()
        )

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region') as mock_route:
            handle_enrollment_for_webhooks(sender=None, signal=None, enrollment=enrollment_data)
            mock_route.assert_not_called()

    def test_handle_grade_change_complete_payload_structure(self):
        """Verify the complete payload structure for grade change events."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_key = CourseKey.from_string('course-v1:edX+DemoX+Demo_Course')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Demo Course'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.85,
            letter_grade='B',
            passed_timestamp=timezone.now()
        )

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region') as mock_route:
            handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

            mock_route.assert_called_once()
            _, kwargs = mock_route.call_args
            payload = kwargs['payload']

            # Verify top-level structure
            assert 'completion' in payload, "Payload must contain 'completion' key"

            # Verify completion data
            completion = payload['completion']
            assert 'percent_grade' in completion
            assert completion['percent_grade'] == 0.85
            assert 'letter_grade' in completion
            assert completion['letter_grade'] == 'B'

            # Verify course information exists (structure may vary)
            assert 'course' in payload and 'course_key' in payload['course']
            assert payload['course']['course_key'] == str(course_key)

            # Verify user information
            assert kwargs['user'] == user
            assert kwargs['course_id'] == str(course_key)

    def test_handle_enrollment_complete_payload_structure(self):
        """Verify the complete payload structure for enrollment events."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_key = CourseKey.from_string('course-v1:edX+DemoX+Demo_Course')

        enrollment_data = CourseEnrollmentData(
            user=UserData(id=user.id, is_active=True, pii=UserPersonalData(username=user.username, email=user.email)),
            course=CourseData(course_key=course_key, display_name='Demo Course'),
            mode='verified',
            is_active=True,
            creation_date=timezone.now()
        )

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region') as mock_route:
            handle_enrollment_for_webhooks(sender=None, signal=None, enrollment=enrollment_data)

            mock_route.assert_called_once()
            _, kwargs = mock_route.call_args
            payload = kwargs['payload']

            # Verify top-level structure
            assert 'enrollment' in payload, "Payload must contain 'enrollment' key"

            # Verify enrollment data
            enrollment = payload['enrollment']
            assert 'mode' in enrollment
            assert enrollment['mode'] == 'verified'

            # Verify course information
            assert kwargs['course_id'] == str(course_key)
            assert kwargs['event_type'] == 'course_enrollment'

    def test_handle_grade_change_logging(self, caplog):
        """Verify appropriate log messages for grade change events."""
        caplog.set_level(logging.INFO)

        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_key = CourseKey.from_string('course-v1:edX+DemoX+Demo_Course')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Demo Course'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.85,
            letter_grade='B',
            passed_timestamp=timezone.now()
        )

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region'):
            handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

        # Verify logging contains relevant information
        assert any('Queued' in record.message or 'webhook' in record.message.lower()
                   for record in caplog.records)

    def test_handle_grade_change_missing_data(self, caplog):
        """Verify handling of grade change events without grade data."""
        caplog.set_level(logging.WARNING)

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region') as mock_route:
            handle_grade_change_for_webhooks(sender=None, signal=None)
            mock_route.assert_not_called()

        # Check for warning log
        assert any('without grade data' in record.message for record in caplog.records)

    def test_handle_enrollment_missing_data(self, caplog):
        """Verify handling of enrollment events without enrollment data."""
        caplog.set_level(logging.WARNING)

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region') as mock_route:
            handle_enrollment_for_webhooks(sender=None, signal=None)
            mock_route.assert_not_called()

        # Check for warning log
        assert any('without enrollment data' in record.message for record in caplog.records)

    def test_handle_grade_change_user_not_found(self, caplog):
        """Verify handling when user does not exist."""
        caplog.set_level(logging.ERROR)

        course_key = CourseKey.from_string('course-v1:edX+DemoX+Demo_Course')
        grade_data = PersistentCourseGradeData(
            user_id=99999,  # Non-existent user
            course=CourseData(course_key=course_key, display_name='Demo Course'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.85,
            letter_grade='B',
            passed_timestamp=timezone.now()
        )

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region') as mock_route:
            handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)
            mock_route.assert_not_called()

        # Check for error log
        assert any('not found' in record.message for record in caplog.records)

    def test_handle_enrollment_user_not_found(self, caplog):
        """Verify handling when user does not exist for enrollment."""
        caplog.set_level(logging.ERROR)

        course_key = CourseKey.from_string('course-v1:edX+DemoX+Demo_Course')

        enrollment_data = CourseEnrollmentData(
            user=UserData(id=99999, is_active=False, pii=UserPersonalData(username='ghost', email='ghost@example.com')),
            course=CourseData(course_key=course_key, display_name='Demo Course'),
            mode='audit',
            is_active=True,
            creation_date=timezone.now()
        )

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region') as mock_route:
            handle_enrollment_for_webhooks(sender=None, signal=None, enrollment=enrollment_data)
            mock_route.assert_not_called()

        # Check for error log
        assert any('not found' in record.message for record in caplog.records)

    def test_handle_grade_change_no_webhook_configured(self, caplog):
        """Verify handling when no webhook is configured (NoWebhookConfigured exception)."""
        caplog.set_level(logging.DEBUG)

        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_key = CourseKey.from_string('course-v1:edX+DemoX+Demo_Course')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Demo Course'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.85,
            letter_grade='B',
            passed_timestamp=timezone.now()
        )

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region') as mock_route:
            mock_route.side_effect = NoWebhookConfigured("No webhook configured for this enterprise")
            handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

        # Check for debug log
        assert any('No webhook configured' in record.message for record in caplog.records)

    def test_handle_grade_change_generic_exception(self, caplog):
        """Verify handling of generic exceptions during grade change processing."""
        caplog.set_level(logging.ERROR)

        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_key = CourseKey.from_string('course-v1:edX+DemoX+Demo_Course')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Demo Course'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.85,
            letter_grade='B',
            passed_timestamp=timezone.now()
        )

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region') as mock_route:
            mock_route.side_effect = RuntimeError("Unexpected error")
            handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

        # Check for error log
        assert any('Failed to queue completion webhook' in record.message for record in caplog.records)

    def test_handle_enrollment_no_webhook_configured(self, caplog):
        """Verify handling when no webhook is configured for enrollment."""
        caplog.set_level(logging.DEBUG)

        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_key = CourseKey.from_string('course-v1:edX+DemoX+Demo_Course')
        enrollment_data = CourseEnrollmentData(
            user=UserData(id=user.id, is_active=True, pii=UserPersonalData(username=user.username, email=user.email)),
            course=CourseData(course_key=course_key, display_name='Demo Course'),
            mode='verified',
            is_active=True,
            creation_date=timezone.now()
        )

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region') as mock_route:
            mock_route.side_effect = NoWebhookConfigured("No webhook configured for this enterprise")
            handle_enrollment_for_webhooks(sender=None, signal=None, enrollment=enrollment_data)

        # Check for debug log
        assert any('No webhook configured' in record.message for record in caplog.records)

    def test_handle_enrollment_generic_exception(self, caplog):
        """Verify handling of generic exceptions during enrollment processing."""
        caplog.set_level(logging.ERROR)

        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_key = CourseKey.from_string('course-v1:edX+DemoX+Demo_Course')
        enrollment_data = CourseEnrollmentData(
            user=UserData(id=user.id, is_active=True, pii=UserPersonalData(username=user.username, email=user.email)),
            course=CourseData(course_key=course_key, display_name='Demo Course'),
            mode='verified',
            is_active=True,
            creation_date=timezone.now()
        )

        with patch('channel_integrations.integrated_channel.handlers.route_webhook_by_region') as mock_route:
            mock_route.side_effect = RuntimeError("Unexpected error")
            handle_enrollment_for_webhooks(sender=None, signal=None, enrollment=enrollment_data)

        # Check for error log
        assert any('Failed to queue enrollment webhook' in record.message for record in caplog.records)
