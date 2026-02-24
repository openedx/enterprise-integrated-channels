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
class TestOAuth2TokenFetching:
    """Tests for OAuth2 token fetching functionality."""

    @responses.activate
    def test_get_oauth_bearer_token_success(self):
        """Verify successful OAuth2 token fetching."""
        enterprise = EnterpriseCustomerFactory()
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            token_api_url='https://auth.example.com/token',
            decrypted_client_id='test_client_id',
            decrypted_client_secret='test_client_secret',
            provider_name='TestProvider'
        )

        # Mock token API response
        responses.add(
            responses.POST,
            'https://auth.example.com/token',
            json={
                'access_token': 'test_bearer_token_12345',
                'token_type': 'Bearer',
                'expires_in': 3600
            },
            status=200
        )

        token = _get_oauth_bearer_token(config)

        assert token == 'test_bearer_token_12345'

        # Verify the request payload
        assert len(responses.calls) == 1
        request_body = responses.calls[0].request.body
        assert b'grant_type' in request_body
        assert b'client_credentials' in request_body
        assert b'test_client_id' in request_body
        assert b'test_client_secret' in request_body
        assert b'TestProvider' in request_body

    @responses.activate
    def test_get_oauth_bearer_token_without_provider_name(self):
        """Verify OAuth2 token fetching works without provider_name."""
        enterprise = EnterpriseCustomerFactory()
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            token_api_url='https://auth.example.com/token',
            decrypted_client_id='test_client_id',
            decrypted_client_secret='test_client_secret',
            provider_name=None  # No provider name
        )

        responses.add(
            responses.POST,
            'https://auth.example.com/token',
            json={'access_token': 'token_without_provider', 'expires_in': 3600},
            status=200
        )

        token = _get_oauth_bearer_token(config)

        assert token == 'token_without_provider'
        request_body = responses.calls[0].request.body
        assert b'provider_name' not in request_body

    @responses.activate
    def test_get_oauth_bearer_token_api_error(self):
        """Verify proper error handling when token API returns error."""
        enterprise = EnterpriseCustomerFactory()
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            token_api_url='https://auth.example.com/token',
            decrypted_client_id='test_client_id',
            decrypted_client_secret='test_client_secret'
        )

        # Mock 401 Unauthorized error
        responses.add(
            responses.POST,
            'https://auth.example.com/token',
            json={'error': 'invalid_client'},
            status=401
        )

        with pytest.raises(requests.exceptions.HTTPError):
            _get_oauth_bearer_token(config)

    @responses.activate
    def test_get_oauth_bearer_token_missing_access_token(self):
        """Verify error handling when response is missing access_token."""
        enterprise = EnterpriseCustomerFactory()
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            token_api_url='https://auth.example.com/token',
            decrypted_client_id='test_client_id',
            decrypted_client_secret='test_client_secret'
        )

        # Mock response without access_token
        responses.add(
            responses.POST,
            'https://auth.example.com/token',
            json={'token_type': 'Bearer', 'expires_in': 3600},
            status=200
        )

        with pytest.raises(ValueError, match="Token API response missing 'access_token'"):
            _get_oauth_bearer_token(config)

    def test_get_oauth_bearer_token_missing_credentials(self):
        """Verify error when OAuth2 credentials are not configured."""
        enterprise = EnterpriseCustomerFactory()

        # Test missing token_api_url
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            token_api_url=None,
            decrypted_client_id='test_client_id',
            decrypted_client_secret='test_client_secret'
        )

        with pytest.raises(ValueError, match="Token API URL, client ID, and client secret must be configured"):
            _get_oauth_bearer_token(config)

    @responses.activate
    def test_get_oauth_bearer_token_timeout(self):
        """Verify timeout handling for token API."""
        enterprise = EnterpriseCustomerFactory()
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            token_api_url='https://auth.example.com/token',
            decrypted_client_id='test_client_id',
            decrypted_client_secret='test_client_secret'
        )

        # Mock timeout
        responses.add(
            responses.POST,
            'https://auth.example.com/token',
            body=requests.exceptions.Timeout('Connection timeout')
        )

        with pytest.raises(requests.exceptions.Timeout):
            _get_oauth_bearer_token(config)

    @responses.activate
    def test_webhook_delivery_with_oauth2(self):
        """Integration test: webhook delivery using OAuth2 token."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            token_api_url='https://auth.example.com/token',
            decrypted_client_id='client_123',
            decrypted_client_secret='secret_456',
            provider_name='Skillsoft'
        )

        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-v1:edX+DemoX+Demo',
            event_type='course_completion',
            user_region='US',
            webhook_url=config.webhook_url,
            payload={'content_id': 'course-v1:edX+DemoX+Demo', 'status': 'completed'},
            deduplication_key='oauth-test-key'
        )

        # Mock token API
        responses.add(
            responses.POST,
            'https://auth.example.com/token',
            json={'access_token': 'oauth_token_xyz', 'expires_in': 3600},
            status=200
        )

        # Mock webhook endpoint
        responses.add(
            responses.POST,
            'https://example.com/webhook',
            json={'status': 'received'},
            status=200
        )

        process_webhook_queue(queue_item.id)

        queue_item.refresh_from_db()
        assert queue_item.status == 'success'
        assert queue_item.attempt_count == 1

        # Verify token API was called
        assert len(responses.calls) == 2
        token_request = responses.calls[0]
        assert 'auth.example.com/token' in token_request.request.url

        # Verify webhook was called with OAuth2 token
        webhook_request = responses.calls[1]
        assert webhook_request.request.headers['Authorization'] == 'Bearer oauth_token_xyz'

    @responses.activate
    def test_webhook_fallback_to_static_token(self):
        """Verify fallback to static token when OAuth2 not configured."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')

        # Config with only static token (no OAuth2)
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            webhook_auth_token='static_token_123',
            token_api_url=None  # No OAuth2 configured
        )

        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url=config.webhook_url,
            payload={'event': 'test'},
            deduplication_key='static-token-key'
        )

        # Mock webhook endpoint
        responses.add(
            responses.POST,
            'https://example.com/webhook',
            json={'status': 'ok'},
            status=200
        )

        process_webhook_queue(queue_item.id)

        queue_item.refresh_from_db()
        assert queue_item.status == 'success'

        # Verify static token was used
        assert len(responses.calls) == 1
        assert responses.calls[0].request.headers['Authorization'] == 'Bearer static_token_123'

    @responses.activate
    def test_webhook_oauth2_token_fetch_failure_marks_failed(self):
        """Verify that token fetch failure marks webhook as failed."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook',
            token_api_url='https://auth.example.com/token',
            decrypted_client_id='test_client',
            decrypted_client_secret='test_secret'
        )

        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url=config.webhook_url,
            payload={'event': 'test'},
            deduplication_key='token-fail-key'
        )

        # Mock token API failure
        responses.add(
            responses.POST,
            'https://auth.example.com/token',
            json={'error': 'server_error'},
            status=500
        )

        process_webhook_queue(queue_item.id)

        queue_item.refresh_from_db()
        assert queue_item.status == 'failed'
        assert 'Token API error' in queue_item.error_message
        assert queue_item.http_status_code is None  # Webhook was never called

