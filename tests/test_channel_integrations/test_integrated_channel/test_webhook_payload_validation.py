"""
Integration tests for webhook payload schema validation.

Tests that webhook payloads:
- Match expected schema structure
- Include all required fields
- Use correct data types and formats
- Conform to ISO 8601 timestamps
- Include proper enterprise/learner/course metadata
"""
from datetime import datetime

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

from channel_integrations.integrated_channel.handlers import _prepare_completion_payload, _prepare_enrollment_payload

User = get_user_model()


@pytest.mark.django_db
class TestWebhookPayloadValidation:
    """Test webhook payload schema validation and structure."""

    def test_completion_payload_schema_structure(self):
        """Verify completion payload has correct structure and all required fields."""
        # Setup
        user = User.objects.create(
            username='schema-test',
            email='schema@example.com',
            first_name='Schema',
            last_name='Test'
        )
        course_key = CourseKey.from_string('course-v1:edX+Schema+2024')

        # Create grade data
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(
                course_key=course_key,
                display_name='Schema Validation Course'
            ),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash123',
            percent_grade=0.92,
            letter_grade='A',
            passed_timestamp=timezone.now()
        )

        # Generate payload
        payload = _prepare_completion_payload(grade_data, user)

        # Validate top-level structure
        assert isinstance(payload, dict)

        # Ensure existence of required Percipio fields for Skillsoft
        percipio_required_keys = ['content_id', 'user', 'status', 'event_date',
                                  'completion_percentage']

        for key in percipio_required_keys:
            assert key in payload, f"Missing required top-level key: {key}"

        # Validate top-level required keys
        assert payload['content_id'] == str(course_key)
        assert payload['user'] == user.username
        assert payload['status'] == 'completed'
        assert payload['completion_percentage'] == 100

    def test_completion_payload_data_types(self):
        """Verify completion payload uses correct data types."""
        user = User.objects.create(username='type-test', email='type@example.com')
        course_key = CourseKey.from_string('course-v1:edX+Types+2024')

        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Type Test'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.85,
            letter_grade='B',
            passed_timestamp=timezone.now()
        )

        payload = _prepare_completion_payload(grade_data, user)

        # Validate data types
        assert isinstance(payload['content_id'], str)
        assert isinstance(payload['user'], str)
        assert isinstance(payload['status'], str)
        assert isinstance(payload['event_date'], str)
        assert isinstance(payload['completion_percentage'], int)

    def test_completion_payload_timestamp_format(self):
        """Verify timestamps are in ISO 8601 format."""
        user = User.objects.create(username='timestamp-test', email='ts@example.com')
        course_key = CourseKey.from_string('course-v1:edX+Timestamp+2024')

        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Timestamp Test'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.75,
            letter_grade='C',
            passed_timestamp=timezone.now()
        )

        payload = _prepare_completion_payload(grade_data, user)

        # Validate event_date format (ISO 8601)
        # Should not raise ValueError
        event_date = datetime.fromisoformat(payload['event_date'].replace('Z', '+00:00'))
        assert isinstance(event_date, datetime)

    def test_enrollment_payload_schema_structure(self):
        """Verify enrollment payload has correct structure."""
        user = User.objects.create(username='enroll-schema', email='enroll@example.com')
        course_key = CourseKey.from_string('course-v1:edX+EnrollSchema+2024')

        # Create enrollment data
        enrollment_data = CourseEnrollmentData(
            user=UserData(
                id=user.id,
                is_active=True,
                pii=UserPersonalData(
                    username=user.username,
                    email=user.email,
                    name='Enrollment Test User'
                )
            ),
            course=CourseData(
                course_key=course_key,
                display_name='Enrollment Schema Test'
            ),
            mode='verified',
            is_active=True,
            creation_date=timezone.now()
        )

        # Generate payload
        payload = _prepare_enrollment_payload(enrollment_data, user)

        # Ensure existence of required Percipio fields for Skillsoft
        percipio_required_keys = ['content_id', 'user', 'status', 'event_date',
                                  'completion_percentage']

        for key in percipio_required_keys:
            assert key in payload, f"Missing required top-level key: {key}"

        # Validate top-level required keys
        assert payload['content_id'] == str(course_key)
        assert payload['user'] == user.username
        assert payload['status'] == 'started'
        assert payload['completion_percentage'] == 0

    def test_enrollment_payload_timestamp_format(self):
        """Verify enrollment timestamps are in ISO 8601 format."""
        user = User.objects.create(username='enroll-ts', email='enrollts@example.com')
        course_key = CourseKey.from_string('course-v1:edX+EnrollTS+2024')

        enrollment_data = CourseEnrollmentData(
            user=UserData(
                id=user.id,
                is_active=True,
                pii=UserPersonalData(
                    username=user.username,
                    email=user.email,
                    name='TS Test'
                )
            ),
            course=CourseData(course_key=course_key, display_name='Enrollment TS'),
            mode='verified',
            is_active=True,
            creation_date=timezone.now()
        )

        payload = _prepare_enrollment_payload(enrollment_data, user)

        # Validate enrollment_date format (ISO 8601)
        event_date = datetime.fromisoformat(payload['event_date'].replace('Z', '+00:00'))
        assert isinstance(event_date, datetime)
