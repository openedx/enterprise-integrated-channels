"""
Integration tests for webhook payload schema validation.

Tests that webhook payloads:
- Match expected schema structure
- Include all required fields
- Use correct data types and formats
- Conform to ISO 8601 timestamps
- Include proper enterprise/learner/course metadata
"""
import json
from datetime import datetime
from uuid import UUID

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
from test_utils.factories import EnterpriseCustomerFactory

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
        enterprise = EnterpriseCustomerFactory(name='Test Enterprise')
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
        payload = _prepare_completion_payload(grade_data, user, enterprise)

        # Validate top-level structure
        assert isinstance(payload, dict)
        required_top_keys = ['event_type', 'event_version', 'event_source', 'timestamp',
                             'enterprise_customer', 'learner', 'course', 'completion']
        for key in required_top_keys:
            assert key in payload, f"Missing required top-level key: {key}"

        # Validate event metadata
        assert payload['event_type'] == 'course_completion'
        assert payload['event_version'] == '2.0'
        assert payload['event_source'] == 'openedx_events'

        # Validate enterprise_customer section
        assert 'uuid' in payload['enterprise_customer']
        assert 'name' in payload['enterprise_customer']
        assert payload['enterprise_customer']['uuid'] == str(enterprise.uuid)
        assert payload['enterprise_customer']['name'] == enterprise.name

        # Validate learner section
        assert 'user_id' in payload['learner']
        assert 'username' in payload['learner']
        assert 'email' in payload['learner']
        assert payload['learner']['user_id'] == user.id
        assert payload['learner']['username'] == user.username
        assert payload['learner']['email'] == user.email

        # Validate course section
        assert 'course_key' in payload['course']
        assert payload['course']['course_key'] == str(course_key)

        # Validate completion section
        completion_keys = ['completed', 'completion_date', 'percent_grade', 'letter_grade', 'is_passing']
        for key in completion_keys:
            assert key in payload['completion'], f"Missing completion field: {key}"

    def test_completion_payload_data_types(self):
        """Verify completion payload uses correct data types."""
        user = User.objects.create(username='type-test', email='type@example.com')
        enterprise = EnterpriseCustomerFactory()
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

        payload = _prepare_completion_payload(grade_data, user, enterprise)

        # Validate data types
        assert isinstance(payload['event_type'], str)
        assert isinstance(payload['event_version'], str)
        assert isinstance(payload['timestamp'], str)

        assert isinstance(payload['enterprise_customer']['uuid'], str)
        assert isinstance(payload['enterprise_customer']['name'], str)

        assert isinstance(payload['learner']['user_id'], int)
        assert isinstance(payload['learner']['username'], str)
        assert isinstance(payload['learner']['email'], str)

        assert isinstance(payload['course']['course_key'], str)

        assert isinstance(payload['completion']['completed'], bool)
        assert isinstance(payload['completion']['completion_date'], str)
        assert isinstance(payload['completion']['percent_grade'], float)
        assert isinstance(payload['completion']['letter_grade'], str)
        assert isinstance(payload['completion']['is_passing'], bool)

    def test_completion_payload_timestamp_format(self):
        """Verify timestamps are in ISO 8601 format."""
        user = User.objects.create(username='timestamp-test', email='ts@example.com')
        enterprise = EnterpriseCustomerFactory()
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

        payload = _prepare_completion_payload(grade_data, user, enterprise)

        # Validate timestamp format (ISO 8601)
        # Should not raise ValueError
        timestamp = datetime.fromisoformat(payload['timestamp'].replace('Z', '+00:00'))
        assert isinstance(timestamp, datetime)

        # Validate completion_date format
        completion_date = datetime.fromisoformat(payload['completion']['completion_date'].replace('Z', '+00:00'))
        assert isinstance(completion_date, datetime)

    def test_completion_payload_percent_grade_range(self):
        """Verify percent_grade is in valid range 0.0-1.0."""
        user = User.objects.create(username='range-test', email='range@example.com')
        enterprise = EnterpriseCustomerFactory()
        course_key = CourseKey.from_string('course-v1:edX+Range+2024')

        # Test various grade values
        test_grades = [0.0, 0.5, 0.99, 1.0]

        for grade_value in test_grades:
            grade_data = PersistentCourseGradeData(
                user_id=user.id,
                course=CourseData(course_key=course_key, display_name='Range Test'),
                course_edited_timestamp=timezone.now(),
                course_version='1',
                grading_policy_hash='hash',
                percent_grade=grade_value,
                letter_grade='A',
                passed_timestamp=timezone.now()
            )

            payload = _prepare_completion_payload(grade_data, user, enterprise)

            assert 0.0 <= payload['completion']['percent_grade'] <= 1.0
            assert payload['completion']['percent_grade'] == grade_value

    def test_completion_payload_enterprise_uuid_format(self):
        """Verify enterprise UUID is properly formatted."""
        user = User.objects.create(username='uuid-test', email='uuid@example.com')
        enterprise = EnterpriseCustomerFactory()
        course_key = CourseKey.from_string('course-v1:edX+UUID+2024')

        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='UUID Test'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.88,
            letter_grade='B+',
            passed_timestamp=timezone.now()
        )

        payload = _prepare_completion_payload(grade_data, user, enterprise)

        # Validate UUID format - should not raise ValueError
        enterprise_uuid = UUID(payload['enterprise_customer']['uuid'])
        assert str(enterprise_uuid) == str(enterprise.uuid)

    def test_enrollment_payload_schema_structure(self):
        """Verify enrollment payload has correct structure."""
        user = User.objects.create(username='enroll-schema', email='enroll@example.com')
        enterprise = EnterpriseCustomerFactory(name='Enrollment Test Enterprise')
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
        payload = _prepare_enrollment_payload(enrollment_data, user, enterprise)

        # Validate top-level structure
        required_keys = ['event_type', 'event_version', 'event_source', 'timestamp',
                         'enterprise_customer', 'learner', 'course', 'enrollment']
        for key in required_keys:
            assert key in payload, f"Missing required key: {key}"

        # Validate event metadata
        assert payload['event_type'] == 'course_enrollment'
        assert payload['event_version'] == '2.0'
        assert payload['event_source'] == 'openedx_events'

        # Validate enrollment section
        assert 'mode' in payload['enrollment']
        assert 'is_active' in payload['enrollment']
        assert 'enrollment_date' in payload['enrollment']

    def test_enrollment_payload_data_types(self):
        """Verify enrollment payload uses correct data types."""
        user = User.objects.create(username='enroll-types', email='enrolltype@example.com')
        enterprise = EnterpriseCustomerFactory()
        course_key = CourseKey.from_string('course-v1:edX+EnrollTypes+2024')

        enrollment_data = CourseEnrollmentData(
            user=UserData(
                id=user.id,
                is_active=True,
                pii=UserPersonalData(
                    username=user.username,
                    email=user.email,
                    name='Type Test'
                )
            ),
            course=CourseData(course_key=course_key, display_name='Enrollment Type Test'),
            mode='audit',
            is_active=True,
            creation_date=timezone.now()
        )

        payload = _prepare_enrollment_payload(enrollment_data, user, enterprise)

        # Validate enrollment data types
        assert isinstance(payload['enrollment']['mode'], str)
        assert isinstance(payload['enrollment']['is_active'], bool)
        assert isinstance(payload['enrollment']['enrollment_date'], str)

        # Validate mode is one of expected values
        assert payload['enrollment']['mode'] in ['audit', 'verified', 'honor', 'professional', 'no-id-professional']

    def test_enrollment_payload_timestamp_format(self):
        """Verify enrollment timestamps are in ISO 8601 format."""
        user = User.objects.create(username='enroll-ts', email='enrollts@example.com')
        enterprise = EnterpriseCustomerFactory()
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

        payload = _prepare_enrollment_payload(enrollment_data, user, enterprise)

        # Validate enrollment_date format (ISO 8601)
        enrollment_date = datetime.fromisoformat(payload['enrollment']['enrollment_date'].replace('Z', '+00:00'))
        assert isinstance(enrollment_date, datetime)

    def test_course_key_format_validation(self):
        """Verify course keys are properly formatted as strings."""
        user = User.objects.create(username='coursekey-test', email='ck@example.com')
        enterprise = EnterpriseCustomerFactory()

        # Test various course key formats
        course_keys = [
            'course-v1:edX+DemoX+2024',
            'course-v1:HarvardX+CS50+2023',
            'course-v1:MITx+6.00.1x+1T2024',
        ]

        for course_key_str in course_keys:
            course_key = CourseKey.from_string(course_key_str)
            grade_data = PersistentCourseGradeData(
                user_id=user.id,
                course=CourseData(course_key=course_key, display_name='Course Key Test'),
                course_edited_timestamp=timezone.now(),
                course_version='1',
                grading_policy_hash='hash',
                percent_grade=0.80,
                letter_grade='B',
                passed_timestamp=timezone.now()
            )

            payload = _prepare_completion_payload(grade_data, user, enterprise)

            # Verify course key is a string and matches original
            assert isinstance(payload['course']['course_key'], str)
            assert payload['course']['course_key'] == course_key_str

    def test_payload_no_pii_leakage_in_unexpected_fields(self):
        """Verify payload doesn't leak PII in unexpected places."""
        user = User.objects.create(
            username='pii-test',
            email='pii@example.com',
            first_name='Sensitive',
            last_name='Data'
        )
        enterprise = EnterpriseCustomerFactory()
        course_key = CourseKey.from_string('course-v1:edX+PII+2024')

        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='PII Test'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.95,
            letter_grade='A',
            passed_timestamp=timezone.now()
        )

        payload = _prepare_completion_payload(grade_data, user, enterprise)

        # Verify PII is only in expected locations
        # Should have email in learner section
        assert payload['learner']['email'] == user.email

        # Should NOT have email anywhere else in payload
        payload_str = json.dumps(payload)

        # Email should appear only in the learner section
        # Count occurrences of email in serialized payload
        email_count = payload_str.count(user.email)
        assert email_count == 1, "Email appears in unexpected locations in payload"

    def test_payload_boolean_values_are_proper_booleans(self):
        """Verify boolean fields use proper boolean types, not strings."""
        user = User.objects.create(username='bool-test', email='bool@example.com')
        enterprise = EnterpriseCustomerFactory()
        course_key = CourseKey.from_string('course-v1:edX+Bool+2024')

        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Bool Test'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.90,
            letter_grade='A-',
            passed_timestamp=timezone.now()
        )

        payload = _prepare_completion_payload(grade_data, user, enterprise)

        # Verify boolean fields are actual booleans
        assert payload['completion']['completed'] is True
        assert isinstance(payload['completion']['completed'], bool)

        assert payload['completion']['is_passing'] is True
        assert isinstance(payload['completion']['is_passing'], bool)

        # Should not be strings 'true' or 'True'
        assert payload['completion']['completed'] != 'true'
        assert payload['completion']['is_passing'] != 'True'

    def test_payload_serializable_to_json(self):
        """Verify payload can be serialized to JSON without errors."""
        user = User.objects.create(username='json-test', email='json@example.com')
        enterprise = EnterpriseCustomerFactory()
        course_key = CourseKey.from_string('course-v1:edX+JSON+2024')

        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='JSON Test'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.87,
            letter_grade='B+',
            passed_timestamp=timezone.now()
        )

        payload = _prepare_completion_payload(grade_data, user, enterprise)

        # Should serialize without errors
        json_str = json.dumps(payload)
        assert isinstance(json_str, str)

        # Should deserialize back to same structure
        deserialized = json.loads(json_str)
        assert deserialized['event_type'] == payload['event_type']
        assert deserialized['learner']['user_id'] == payload['learner']['user_id']
