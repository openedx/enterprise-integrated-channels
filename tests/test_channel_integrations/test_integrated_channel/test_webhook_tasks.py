"""
Tests for Webhook delivery Celery task.
"""
import logging
from unittest.mock import patch

import pytest
import requests
import responses
from django.contrib.auth import get_user_model

from channel_integrations.integrated_channel.models import EnterpriseWebhookConfiguration, WebhookTransmissionQueue
from channel_integrations.integrated_channel.tasks import process_webhook_queue
from test_utils.factories import EnterpriseCustomerFactory

User = get_user_model()

DEFAULT_PERCIPIO_TOKEN_URLS = {
    'US': 'https://oauth2-provider.percipio.com/oauth2-provider/token',
    'EU': 'https://euc1-prod-oauth2-provider.percipio.com/oauth2-provider/token',
    'OTHER': 'https://oauth2-provider.develop.squads-dev.com/oauth2-provider/token',
}


@pytest.mark.django_db
class TestWebhookTasks:
    """Tests for tasks.py."""

    @responses.activate
    def test_process_webhook_queue_success(self):
        """Verify successful webhook delivery."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            webhook_auth_token='test-token'
        )

        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url=config.webhook_url,
            payload={'event': 'test'},
            deduplication_key='key1'
        )

        responses.add(
            responses.POST,
            config.webhook_url,
            json={'status': 'ok'},
            status=200
        )

        process_webhook_queue(queue_item.id)

        queue_item.refresh_from_db()
        assert queue_item.status == 'success'
        assert queue_item.http_status_code == 200
        assert queue_item.attempt_count == 1
        assert queue_item.completed_at is not None

        # Verify headers
        assert responses.calls[0].request.headers['Authorization'] == 'Bearer test-token'
        assert responses.calls[0].request.headers['User-Agent'] == 'OpenEdX-Enterprise-Webhook/1.0'

    @responses.activate
    def test_process_webhook_queue_retry(self):
        """Verify that failed delivery schedules a retry."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            webhook_retry_attempts=3
        )

        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url=config.webhook_url,
            payload={'event': 'test'},
            deduplication_key='key2'
        )

        # Simulate 500 error
        responses.add(
            responses.POST,
            config.webhook_url,
            status=500
        )

        with patch('channel_integrations.integrated_channel.tasks.process_webhook_queue.apply_async') as mock_apply:
            process_webhook_queue(queue_item.id)

            queue_item.refresh_from_db()
            assert queue_item.status == 'pending'  # Set back to pending for retry
            assert queue_item.attempt_count == 1
            assert queue_item.next_retry_at is not None
            mock_apply.assert_called_once()

    @responses.activate
    def test_process_webhook_queue_max_retries(self):
        """Verify that max retries are respected."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            webhook_retry_attempts=1
        )

        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url=config.webhook_url,
            payload={'event': 'test'},
            deduplication_key='key3',
            attempt_count=1  # Already tried once
        )

        responses.add(responses.POST, config.webhook_url, status=500)

        with patch('channel_integrations.integrated_channel.tasks.process_webhook_queue.apply_async') as mock_apply:
            process_webhook_queue(queue_item.id)

            queue_item.refresh_from_db()
            assert queue_item.status == 'failed'
            assert queue_item.attempt_count == 2
            mock_apply.assert_not_called()

    def test_process_webhook_queue_no_config(self):
        """Verify handling when configuration is missing during processing."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')

        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url='https://example.com/webhook',
            payload={'event': 'test'},
            deduplication_key='key4'
        )

        # No EnterpriseWebhookConfiguration exists
        process_webhook_queue(queue_item.id)

        queue_item.refresh_from_db()
        assert queue_item.status == 'failed'
        assert "No active webhook configuration found" in queue_item.error_message

    @responses.activate
    def test_process_webhook_queue_timeout(self):
        """Verify that timeout errors schedule a retry."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            webhook_retry_attempts=3
        )

        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url=config.webhook_url,
            payload={'event': 'test'},
            deduplication_key='key5'
        )

        # Simulate timeout
        responses.add(
            responses.POST,
            config.webhook_url,
            body=requests.Timeout()
        )

        with patch('channel_integrations.integrated_channel.tasks.process_webhook_queue.apply_async') as mock_apply:
            process_webhook_queue(queue_item.id)

            queue_item.refresh_from_db()
            assert queue_item.status == 'pending'
            assert queue_item.attempt_count == 1
            assert queue_item.next_retry_at is not None
            assert 'Timeout' in queue_item.error_message or 'timed out' in queue_item.error_message.lower()
            mock_apply.assert_called_once()

    @responses.activate
    def test_process_webhook_queue_connection_error(self):
        """Verify that connection errors schedule a retry."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            webhook_retry_attempts=3
        )

        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url=config.webhook_url,
            payload={'event': 'test'},
            deduplication_key='key6'
        )

        # Simulate connection error
        responses.add(
            responses.POST,
            config.webhook_url,
            body=requests.ConnectionError()
        )

        with patch('channel_integrations.integrated_channel.tasks.process_webhook_queue.apply_async') as mock_apply:
            process_webhook_queue(queue_item.id)

            queue_item.refresh_from_db()
            assert queue_item.status == 'pending'
            assert queue_item.attempt_count == 1
            assert queue_item.next_retry_at is not None
            assert 'Connection' in queue_item.error_message or 'connection' in queue_item.error_message.lower()
            mock_apply.assert_called_once()

    @responses.activate
    def test_process_webhook_queue_response_truncation(self):
        """Verify that response body is truncated to 10KB."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook'
        )

        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url=config.webhook_url,
            payload={'event': 'test'},
            deduplication_key='key7'
        )

        # Create a response body larger than 10KB
        large_response_body = 'x' * 20000  # 20KB
        responses.add(
            responses.POST,
            config.webhook_url,
            body=large_response_body,
            status=200
        )

        process_webhook_queue(queue_item.id)

        queue_item.refresh_from_db()
        assert queue_item.status == 'success'
        assert len(queue_item.response_body) == 10000
        assert queue_item.response_body == 'x' * 10000

    @responses.activate
    def test_process_webhook_queue_4xx_errors(self):
        """Verify that 4xx client errors are handled correctly."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            webhook_retry_attempts=3
        )

        test_cases = [
            (400, 'Bad Request'),
            (401, 'Unauthorized'),
            (403, 'Forbidden'),
            (404, 'Not Found'),
            (429, 'Too Many Requests'),
        ]

        for status_code, description in test_cases:
            queue_item = WebhookTransmissionQueue.objects.create(
                enterprise_customer=enterprise,
                user=user,
                course_id='course-id',
                event_type='course_completion',
                user_region='US',
                webhook_url=config.webhook_url,
                payload={'event': 'test'},
                deduplication_key=f'key-4xx-{status_code}'
            )

            responses.add(
                responses.POST,
                config.webhook_url,
                body=description,
                status=status_code
            )

            with patch('channel_integrations.integrated_channel.tasks.process_webhook_queue.apply_async') as mock_apply:
                process_webhook_queue(queue_item.id)

                queue_item.refresh_from_db()
                assert queue_item.http_status_code == status_code
                assert queue_item.status == 'pending'  # Scheduled for retry
                assert queue_item.attempt_count == 1
                mock_apply.assert_called_once()

            responses.reset()

    @responses.activate
    def test_process_webhook_queue_5xx_errors(self):
        """Verify that 5xx server errors are handled correctly."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            webhook_retry_attempts=3
        )

        test_cases = [
            (500, 'Internal Server Error'),
            (502, 'Bad Gateway'),
            (503, 'Service Unavailable'),
            (504, 'Gateway Timeout'),
        ]

        for status_code, description in test_cases:
            queue_item = WebhookTransmissionQueue.objects.create(
                enterprise_customer=enterprise,
                user=user,
                course_id='course-id',
                event_type='course_completion',
                user_region='US',
                webhook_url=config.webhook_url,
                payload={'event': 'test'},
                deduplication_key=f'key-5xx-{status_code}'
            )

            responses.add(
                responses.POST,
                config.webhook_url,
                body=description,
                status=status_code
            )

            with patch('channel_integrations.integrated_channel.tasks.process_webhook_queue.apply_async') as mock_apply:
                process_webhook_queue(queue_item.id)

                queue_item.refresh_from_db()
                assert queue_item.http_status_code == status_code
                assert queue_item.status == 'pending'  # Scheduled for retry
                assert queue_item.attempt_count == 1
                mock_apply.assert_called_once()

            responses.reset()

    @responses.activate
    def test_exponential_backoff_delays(self):
        """Verify that retry delays follow exponential backoff."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            webhook_retry_attempts=5
        )

        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url=config.webhook_url,
            payload={'event': 'test'},
            deduplication_key='key-backoff'
        )

        responses.add(responses.POST, config.webhook_url, status=500)

        expected_delays = [30, 60, 120, 240, 480]  # Exponential: 30 * 2^(n-1)

        for attempt, expected_delay in enumerate(expected_delays, start=1):
            with patch('channel_integrations.integrated_channel.tasks.process_webhook_queue.apply_async') as mock_apply:
                process_webhook_queue(queue_item.id)

                queue_item.refresh_from_db()
                assert queue_item.attempt_count == attempt

                if attempt <= config.webhook_retry_attempts:
                    # Verify countdown parameter
                    mock_apply.assert_called_once()
                    call_args = mock_apply.call_args
                    assert call_args[1]['countdown'] == expected_delay

    @responses.activate
    def test_exponential_backoff_cap_at_one_hour(self):
        """Verify that retry delays are capped at 1 hour (3600 seconds)."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            webhook_retry_attempts=10
        )

        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url=config.webhook_url,
            payload={'event': 'test'},
            deduplication_key='key-backoff-cap',
            attempt_count=7  # 30 * 2^7 = 3840, which exceeds 3600
        )

        responses.add(responses.POST, config.webhook_url, status=500)

        with patch('channel_integrations.integrated_channel.tasks.process_webhook_queue.apply_async') as mock_apply:
            process_webhook_queue(queue_item.id)

            queue_item.refresh_from_db()
            assert queue_item.attempt_count == 8

            # Verify countdown is capped at 3600 seconds
            call_args = mock_apply.call_args
            assert call_args[1]['countdown'] == 3600

    def test_process_webhook_queue_logging(self, caplog):
        """Verify that appropriate log messages are generated."""
        caplog.set_level(logging.INFO)

        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')

        # Test case 1: Queue item not found
        process_webhook_queue(99999)
        assert "Queue item 99999 not found" in caplog.text

        caplog.clear()

        # Test case 2: Missing configuration
        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url='https://example.com/webhook',
            payload={'event': 'test'},
            deduplication_key='key-logging'
        )

        process_webhook_queue(queue_item.id)
        assert "No active webhook configuration found" in caplog.text or "Error processing" in caplog.text

    def test_process_webhook_queue_skips_completed_items(self):
        """
        Verify that queue items with success or cancelled status are not reprocessed.
        This tests the early return path in process_webhook_queue for already-completed items.
        """
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser_completed')

        # Test case 1: Queue item with 'success' status
        success_queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url='https://example.com/webhook',
            payload={'event': 'test'},
            deduplication_key='key-success',
            status='success',
            attempt_count=1
        )

        # Call process_webhook_queue - should return early without processing
        process_webhook_queue(success_queue_item.id)

        # Verify the item was not modified (attempt_count should still be 1)
        success_queue_item.refresh_from_db()
        assert success_queue_item.attempt_count == 1
        assert success_queue_item.status == 'success'

        # Test case 2: Queue item with 'cancelled' status
        cancelled_queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id-2',
            event_type='course_completion',
            user_region='US',
            webhook_url='https://example.com/webhook',
            payload={'event': 'test2'},
            deduplication_key='key-cancelled',
            status='cancelled',
            attempt_count=2
        )

        # Call process_webhook_queue - should return early without processing
        process_webhook_queue(cancelled_queue_item.id)

        # Verify the item was not modified (attempt_count should still be 2)
        cancelled_queue_item.refresh_from_db()
        assert cancelled_queue_item.attempt_count == 2
        assert cancelled_queue_item.status == 'cancelled'


@pytest.mark.django_db
class TestWebhookTasksPercipioAuth:
    """Tests for the Percipio OAuth2 token flow in process_webhook_queue."""

    @responses.activate
    def test_process_webhook_queue_uses_percipio_oauth(self):
        """
        When client_id and decrypted_client_secret are set on the config,
        the Authorization header must use the token fetched from PercipioAuthHelper,
        NOT the static webhook_auth_token.
        """
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser_oauth')
        delivery_url = 'https://example.com/webhook'
        EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            # webhook_url points at the Percipio token endpoint for this region
            webhook_url=DEFAULT_PERCIPIO_TOKEN_URLS['US'],
            client_id='test-client-id',
            decrypted_client_secret='test-client-secret',
            # Static token present but should be ignored in favour of OAuth
            webhook_auth_token='old-static-token',
        )
        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-oauth',
            event_type='course_completion',
            user_region='US',
            webhook_url=delivery_url,
            payload={'event': 'test'},
            deduplication_key='key-oauth-1',
        )

        # Mock the Percipio token endpoint
        responses.add(
            responses.POST,
            DEFAULT_PERCIPIO_TOKEN_URLS['US'],
            json={'access_token': 'percipio-oauth-token', 'expires_in': 3600},
            status=200,
        )
        # Mock the actual webhook delivery endpoint
        responses.add(
            responses.POST,
            delivery_url,
            json={'status': 'ok'},
            status=200,
        )

        process_webhook_queue(queue_item.id)

        queue_item.refresh_from_db()
        assert queue_item.status == 'success'

        # The webhook call is the second call (after the token fetch)
        webhook_call = responses.calls[1]
        assert webhook_call.request.headers['Authorization'] == 'Bearer percipio-oauth-token'
        # Static token must NOT be used
        assert webhook_call.request.headers['Authorization'] != 'Bearer old-static-token'

    @responses.activate
    def test_process_webhook_queue_falls_back_to_static_token(self):
        """
        When no Percipio credentials are set on the config, the task falls back
        to the static webhook_auth_token.
        """
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser_fallback')
        delivery_url = 'https://example.com/webhook'
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url=delivery_url,
            webhook_auth_token='fallback-static-token',
        )
        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-fallback',
            event_type='course_enrollment',
            user_region='US',
            webhook_url=config.webhook_url,
            payload={'event': 'test'},
            deduplication_key='key-fallback-1',
        )

        responses.add(
            responses.POST,
            delivery_url,
            json={'status': 'ok'},
            status=200,
        )

        process_webhook_queue(queue_item.id)

        queue_item.refresh_from_db()
        assert queue_item.status == 'success'
        assert responses.calls[0].request.headers['Authorization'] == 'Bearer fallback-static-token'

    @responses.activate
    def test_process_webhook_queue_fails_when_token_fetch_fails(self):
        """
        When the Percipio token endpoint returns an error, the queue item
        should be marked as failed and scheduled for retry.
        """
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser_tokenfail')
        EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url=DEFAULT_PERCIPIO_TOKEN_URLS['US'],
            client_id='test-client-id',
            decrypted_client_secret='test-client-secret',
            webhook_retry_attempts=3,
        )
        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-tokenfail',
            event_type='course_completion',
            user_region='US',
            webhook_url='https://example.com/webhook',
            payload={'event': 'test'},
            deduplication_key='key-tokenfail-1',
        )

        responses.add(
            responses.POST,
            DEFAULT_PERCIPIO_TOKEN_URLS['US'],
            json={'error': 'invalid_client'},
            status=401,
        )

        with patch(
            'channel_integrations.integrated_channel.tasks.process_webhook_queue.apply_async'
        ) as mock_apply:
            process_webhook_queue(queue_item.id)

            queue_item.refresh_from_db()
            assert queue_item.status == 'pending'  # Scheduled for retry
            assert queue_item.attempt_count == 1
            mock_apply.assert_called_once()

    @responses.activate
    def test_process_webhook_queue_eu_region_uses_eu_token_endpoint(self):
        """
        EU-region queue items must fetch a token from the EU token endpoint,
        not the US endpoint.
        """
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser_eu')
        delivery_url = 'https://example.com/webhook'
        EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='EU',
            webhook_url=DEFAULT_PERCIPIO_TOKEN_URLS['EU'],
            client_id='test-client-id',
            decrypted_client_secret='test-client-secret',
        )
        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-eu',
            event_type='course_completion',
            user_region='EU',
            webhook_url=delivery_url,
            payload={'event': 'test'},
            deduplication_key='key-eu-oauth',
        )

        responses.add(
            responses.POST,
            DEFAULT_PERCIPIO_TOKEN_URLS['EU'],
            json={'access_token': 'eu-token', 'expires_in': 3600},
            status=200,
        )
        responses.add(
            responses.POST,
            delivery_url,
            json={'status': 'ok'},
            status=200,
        )

        process_webhook_queue(queue_item.id)

        queue_item.refresh_from_db()
        assert queue_item.status == 'success'
        # First call must have gone to the EU token endpoint
        assert DEFAULT_PERCIPIO_TOKEN_URLS['EU'] in responses.calls[0].request.url
