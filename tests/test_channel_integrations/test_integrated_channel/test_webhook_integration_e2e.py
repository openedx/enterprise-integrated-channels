"""
End-to-End Integration Tests for Webhook System.

Tests the complete flow from event handler invocation through HTTP delivery.
"""
import json

import pytest
import requests
import responses
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
from social_django.models import UserSocialAuth

from channel_integrations.integrated_channel.handlers import (
    handle_enrollment_for_webhooks,
    handle_grade_change_for_webhooks,
)
from channel_integrations.integrated_channel.models import EnterpriseWebhookConfiguration, WebhookTransmissionQueue
from channel_integrations.integrated_channel.tasks import process_webhook_queue
from test_utils.factories import EnterpriseCustomerFactory, EnterpriseCustomerUserFactory

User = get_user_model()


@pytest.mark.django_db
class TestWebhookEndToEndFlow:
    """
    End-to-end integration tests for webhook delivery.

    Tests the complete flow:
    1. Event handler receives data
    2. User region is detected
    3. Webhook configuration is found
    4. Queue item is created
    5. HTTP request is sent
    6. Success/failure is tracked
    """

    @responses.activate
    def test_grade_change_to_webhook_delivery_success(self):
        """Test complete flow: grade event → region detection → webhook delivery."""
        # 1. Setup enterprise with webhook configuration
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        token_url = 'https://token.example.com/token'
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://us.example.com/webhook',
            webhook_token_url=token_url,
            client_id='test-client-id',
            decrypted_client_secret='test-secret',
            active=True
        )

        # 2. Setup SSO metadata for region detection
        UserSocialAuth.objects.create(
            user=user,
            provider='tpa-saml',
            uid='test-uid',
            extra_data={'country': 'US'}  # Region detection Priority #2
        )

        # 3. Mock the token endpoint and the webhook delivery endpoint
        responses.add(
            responses.POST,
            token_url,
            json={'access_token': 'test-token-123', 'expires_in': 3600},
            status=200,
        )
        responses.add(
            responses.POST,
            config.webhook_url,
            json={'status': 'received'},
            status=200
        )

        # 4. Invoke handler with grade change event
        course_key = CourseKey.from_string('course-v1:edX+DemoX+Demo_Course')
        passed_timestamp = timezone.now()
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Demo Course'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash123',
            percent_grade=0.85,
            letter_grade='B',
            passed_timestamp=passed_timestamp
        )

        handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

        # 5. Verify queue item was created
        queue_item = WebhookTransmissionQueue.objects.get(user=user)
        # Note: Celery runs eagerly in tests (CELERY_TASK_ALWAYS_EAGER=True),
        # so the webhook is already processed and shows 'success' status
        assert queue_item.status == 'success'
        assert queue_item.webhook_url == config.webhook_url
        assert queue_item.user_region == 'US'
        assert queue_item.event_type == 'course_completion'
        assert queue_item.course_id == str(course_key)

        # 6. Verify HTTP request was made correctly (Celery already processed it)
        # calls[0] is the token fetch; calls[1] is the webhook delivery
        assert len(responses.calls) == 2
        request = responses.calls[1].request

        # Verify headers
        assert request.headers['Authorization'] == 'Bearer test-token-123'
        assert request.headers['Content-Type'] == 'application/json'
        assert 'OpenEdX-Enterprise-Webhook' in request.headers['User-Agent']

        # Verify body
        body = json.loads(request.body)
        assert body['status'] == 'completed'
        assert body['event_date'] == passed_timestamp.isoformat()

        # 8. Verify queue item marked as success
        queue_item.refresh_from_db()
        assert queue_item.status == 'success'
        assert queue_item.http_status_code == 200
        assert queue_item.completed_at is not None
        assert queue_item.error_message is None
        assert queue_item.attempt_count == 1

    @responses.activate
    def test_enrollment_to_webhook_delivery_success(self):
        """Test complete flow: enrollment event → webhook delivery."""
        # 1. Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='enrollee', email='enrollee@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='EU',
            webhook_url='https://eu.example.com/webhook',
            active=True
        )

        # SSO for EU region
        UserSocialAuth.objects.create(
            user=user,
            provider='tpa-saml',
            uid='test-uid',
            extra_data={'country': 'FR'}  # Maps to EU
        )

        # Mock endpoint
        responses.add(
            responses.POST,
            config.webhook_url,
            json={'ok': True},
            status=201
        )

        # 2. Invoke handler
        course_key = CourseKey.from_string('course-v1:edX+CS101+2024')
        enrollment_data = CourseEnrollmentData(
            user=UserData(
                id=user.id,
                is_active=True,
                pii=UserPersonalData(
                    username=user.username,
                    email=user.email,
                    name='Test User'
                )
            ),
            course=CourseData(course_key=course_key, display_name='CS101'),
            mode='verified',
            is_active=True,
            creation_date=timezone.now()
        )

        handle_enrollment_for_webhooks(sender=None, signal=None, enrollment=enrollment_data)

        # 3. Verify queue
        queue_item = WebhookTransmissionQueue.objects.get(user=user)
        assert queue_item.event_type == 'course_enrollment'
        assert queue_item.user_region == 'EU'

        # 4. Process
        process_webhook_queue(queue_item.id)

        # 5. Verify success
        assert len(responses.calls) == 1
        queue_item.refresh_from_db()
        assert queue_item.status == 'success'
        assert queue_item.http_status_code == 201

    @responses.activate
    def test_webhook_delivery_with_http_500_triggers_retry(self):
        """Test that HTTP 500 errors trigger retry logic."""
        # Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='retryuser', email='retry@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='OTHER',
            webhook_url='https://other.example.com/webhook',
            active=True
        )

        # Mock 500 error
        responses.add(
            responses.POST,
            config.webhook_url,
            json={'error': 'Internal Server Error'},
            status=500
        )

        # Create grade event
        course_key = CourseKey.from_string('course-v1:edX+Test+2024')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Test'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.90,
            letter_grade='A',
            passed_timestamp=timezone.now()
        )

        handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

        # Note: Celery runs eagerly and already attempted delivery (which failed)
        queue_item = WebhookTransmissionQueue.objects.get(user=user)

        # Verify failure response was recorded and retry is scheduled
        # Status is 'pending' because retries are remaining (not exhausted yet)
        assert queue_item.status == 'pending'  # Will retry
        assert queue_item.http_status_code == 500
        assert queue_item.error_message == 'HTTP 500'
        assert queue_item.attempt_count >= 1  # At least one attempt was made
        assert queue_item.next_retry_at is not None  # Retry scheduled
        assert queue_item.attempt_count == 1

    @responses.activate
    def test_webhook_delivery_timeout_handling(self):
        """Test that connection timeouts are handled properly."""
        # Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='timeoutuser', email='timeout@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='OTHER',
            webhook_url='https://timeout.example.com/webhook',
            webhook_timeout_seconds=1,
            active=True
        )

        # Mock timeout exception
        def timeout_callback(request):
            raise requests.exceptions.Timeout('Connection timeout')

        responses.add_callback(
            responses.POST,
            config.webhook_url,
            callback=timeout_callback
        )

        # Create event
        course_key = CourseKey.from_string('course-v1:edX+Timeout+2024')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Timeout Test'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=1.0,
            letter_grade='A',
            passed_timestamp=timezone.now()
        )

        handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

        # Note: Celery runs eagerly and already attempted delivery (which timed out)
        queue_item = WebhookTransmissionQueue.objects.get(user=user)

        # Verify timeout error was recorded and retry is scheduled
        # Status is 'pending' because retries are remaining (not exhausted yet)
        assert queue_item.status == 'pending'  # Will retry
        assert 'timeout' in queue_item.error_message.lower()
        assert queue_item.attempt_count >= 1  # At least one attempt was made
        assert queue_item.next_retry_at is not None  # Retry scheduled

    @responses.activate
    def test_webhook_with_no_auth_token(self):
        """Test webhook delivery without authentication token."""
        # Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='noauthuser', email='noauth@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='OTHER',
            webhook_url='https://noauth.example.com/webhook',
            active=True
        )

        # Mock endpoint
        responses.add(
            responses.POST,
            config.webhook_url,
            json={'received': True},
            status=200
        )

        # Create event
        course_key = CourseKey.from_string('course-v1:edX+NoAuth+2024')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='No Auth'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash',
            percent_grade=0.75,
            letter_grade='C',
            passed_timestamp=timezone.now()
        )

        handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)
        queue_item = WebhookTransmissionQueue.objects.get(user=user)

        # Process
        process_webhook_queue(queue_item.id)

        # Verify no Authorization header sent
        assert len(responses.calls) == 1
        request = responses.calls[0].request
        assert 'Authorization' not in request.headers

        queue_item.refresh_from_db()
        assert queue_item.status == 'success'

    @responses.activate
    def test_multiple_webhooks_for_different_regions(self):
        """Test that different regions get routed to correct webhooks."""
        # Setup enterprise with multiple region configs
        enterprise = EnterpriseCustomerFactory()

        # US user
        us_user = User.objects.create(username='ususer', email='us@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=us_user.id)
        UserSocialAuth.objects.create(
            user=us_user,
            provider='tpa-saml',
            uid='us-uid',
            extra_data={'country': 'US'}
        )

        # EU user
        eu_user = User.objects.create(username='euuser', email='eu@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=eu_user.id)
        UserSocialAuth.objects.create(
            user=eu_user,
            provider='tpa-saml',
            uid='eu-uid',
            extra_data={'country': 'DE'}  # Maps to EU
        )

        # Region configs
        us_config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://us.example.com/webhook',
            active=True
        )

        eu_config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='EU',
            webhook_url='https://eu.example.com/webhook',
            active=True
        )

        # Mock both endpoints
        responses.add(responses.POST, us_config.webhook_url, json={'ok': True}, status=200)
        responses.add(responses.POST, eu_config.webhook_url, json={'ok': True}, status=200)

        # Create events for both users
        course_key = CourseKey.from_string('course-v1:edX+Multi+2024')

        for user in [us_user, eu_user]:
            grade_data = PersistentCourseGradeData(
                user_id=user.id,
                course=CourseData(course_key=course_key, display_name='Multi Region'),
                course_edited_timestamp=timezone.now(),
                course_version='1',
                grading_policy_hash='hash',
                percent_grade=0.80,
                letter_grade='B',
                passed_timestamp=timezone.now()
            )
            handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

        # Verify queue items
        us_queue = WebhookTransmissionQueue.objects.get(user=us_user)
        eu_queue = WebhookTransmissionQueue.objects.get(user=eu_user)

        assert us_queue.webhook_url == us_config.webhook_url
        assert us_queue.user_region == 'US'

        assert eu_queue.webhook_url == eu_config.webhook_url
        assert eu_queue.user_region == 'EU'

        # Process both
        process_webhook_queue(us_queue.id)
        process_webhook_queue(eu_queue.id)

        # Verify both succeeded with correct endpoints
        assert len(responses.calls) == 2

        us_call = next(c for c in responses.calls if 'us.example.com' in c.request.url)
        eu_call = next(c for c in responses.calls if 'eu.example.com' in c.request.url)

        assert us_call is not None
        assert eu_call is not None

        us_queue.refresh_from_db()
        eu_queue.refresh_from_db()

        assert us_queue.status == 'success'
        assert eu_queue.status == 'success'
