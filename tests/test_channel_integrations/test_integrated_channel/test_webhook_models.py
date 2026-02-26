"""
Tests for Enterprise Webhook models.
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from freezegun import freeze_time

from channel_integrations.integrated_channel.models import EnterpriseWebhookConfiguration, WebhookTransmissionQueue
from channel_integrations.integrated_channel.services.webhook_routing import route_webhook_by_region
from test_utils.factories import EnterpriseCustomerFactory

User = get_user_model()


@pytest.mark.django_db
class TestEnterpriseWebhookConfiguration:
    """Tests for EnterpriseWebhookConfiguration model."""

    def test_https_requirement(self):
        """Verify that webhook URL must use HTTPS."""
        enterprise = EnterpriseCustomerFactory()
        config = EnterpriseWebhookConfiguration(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='http://example.com/webhook'
        )
        with pytest.raises(ValidationError, match='Webhook URL must use HTTPS'):
            config.clean()

    def test_ssrf_protection_private_ip(self):
        """Verify that private IP ranges are blocked."""
        enterprise = EnterpriseCustomerFactory()
        for ip in ['10.0.0.1', '172.16.0.1', '192.168.1.1']:
            config = EnterpriseWebhookConfiguration(
                enterprise_customer=enterprise,
                region='US',
                webhook_url=f'https://{ip}/webhook'
            )
            with pytest.raises(ValidationError, match='private or reserved IP'):
                config.clean()

    def test_ssrf_protection_localhost_hostnames(self):
        """Verify that localhost and loopback hostnames are blocked."""
        enterprise = EnterpriseCustomerFactory()
        # Test localhost and IPv4 loopback addresses
        for host in ['localhost', '127.0.0.1', '0.0.0.0']:
            config = EnterpriseWebhookConfiguration(
                enterprise_customer=enterprise,
                region='US',
                webhook_url=f'https://{host}/webhook'
            )
            with pytest.raises(ValidationError, match='cannot point to localhost or loopback'):
                config.clean()

        # Test IPv6 loopback (needs brackets in URL)
        config = EnterpriseWebhookConfiguration(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://[::1]/webhook'
        )
        with pytest.raises(ValidationError, match='cannot point to localhost or loopback'):
            config.clean()

    def test_ssrf_protection_cloud_metadata_ip(self):
        """Verify that cloud metadata IP address is blocked as a private IP."""
        enterprise = EnterpriseCustomerFactory()
        config = EnterpriseWebhookConfiguration(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://169.254.169.254/latest/meta-data/'
        )
        # Note: 169.254.169.254 is caught by is_private check, not the specific metadata check
        with pytest.raises(ValidationError, match='cannot point to private or reserved IP'):
            config.clean()

    def test_invalid_webhook_url_no_hostname(self):
        """Verify that URLs without a hostname are rejected."""
        enterprise = EnterpriseCustomerFactory()
        config = EnterpriseWebhookConfiguration(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://'
        )
        with pytest.raises(ValidationError, match='Invalid webhook URL'):
            config.clean()

    def test_webhook_url_not_provided(self):
        """Verify that configurations without webhook_url don't raise validation errors."""
        enterprise = EnterpriseCustomerFactory()
        # Test with no webhook_url (should pass validation)
        config = EnterpriseWebhookConfiguration(
            enterprise_customer=enterprise,
            region='US',
            webhook_url=None
        )
        # Should not raise - webhook_url is optional
        config.clean()

        # Test with empty string
        config2 = EnterpriseWebhookConfiguration(
            enterprise_customer=enterprise,
            region='US',
            webhook_url=''
        )
        # Should not raise - empty webhook_url is treated as None
        config2.clean()

    def test_public_ip_address_allowed(self):
        """Verify that public IP addresses are allowed (not private/reserved/loopback)."""
        enterprise = EnterpriseCustomerFactory()
        # Test with a public IP address (Google DNS)
        config = EnterpriseWebhookConfiguration(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://8.8.8.8/webhook'
        )
        # Should not raise - 8.8.8.8 is a public IP
        config.clean()

    def test_valid_config(self):
        """Verify that a valid configuration passes validation."""
        enterprise = EnterpriseCustomerFactory()
        config = EnterpriseWebhookConfiguration(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://api.external-service.com/webhook'
        )
        # Should not raise
        config.clean()


@pytest.mark.django_db
class TestWebhookTransmissionQueue:
    """Tests for WebhookTransmissionQueue model."""

    def test_queue_creation(self):
        """Verify that a queue item can be created."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        queue_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-v1:edX+DemoX+Demo_Course',
            event_type='course_completion',
            user_region='US',
            webhook_url='https://example.com/webhook',
            payload={'foo': 'bar'},
            deduplication_key='test-key'
        )
        assert queue_item.status == 'pending'
        assert queue_item.attempt_count == 0
        assert queue_item.deduplication_key == 'test-key'

    def test_unique_enterprise_region_constraint(self):
        """Verify that unique constraint on (enterprise_customer, region) works."""
        enterprise = EnterpriseCustomerFactory()

        # Create first configuration
        config1 = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://us1.example.com/webhook'
        )

        # Attempt to create duplicate with same enterprise and region
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                EnterpriseWebhookConfiguration.objects.create(
                    enterprise_customer=enterprise,
                    region='US',
                    webhook_url='https://us2.example.com/webhook'
                )

        # Different region should work
        config2 = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='EU',
            webhook_url='https://eu.example.com/webhook'
        )
        assert config2.id != config1.id

    def test_deduplication_key_constraint(self):
        """Verify that deduplication constraint prevents duplicate active items."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')

        # Create first queue item
        item1 = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url='https://example.com/webhook',
            payload={'event': 'test'},
            deduplication_key='dedup-key-1',
            status='pending'
        )

        # Attempt to create duplicate with same key and active status
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                WebhookTransmissionQueue.objects.create(
                    enterprise_customer=enterprise,
                    user=user,
                    course_id='course-id',
                    event_type='course_completion',
                    user_region='US',
                    webhook_url='https://example.com/webhook',
                    payload={'event': 'test'},
                    deduplication_key='dedup-key-1',
                    status='pending'
                )

        # Cancelled status should allow duplicate key
        item2 = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id-2',
            event_type='course_completion',
            user_region='US',
            webhook_url='https://example.com/webhook',
            payload={'event': 'test'},
            deduplication_key='dedup-key-1',
            status='cancelled'
        )
        assert item2.id != item1.id

    def test_webhook_configuration_default_values(self):
        """Verify that default values are set correctly."""
        enterprise = EnterpriseCustomerFactory()
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook'
        )

        assert config.webhook_timeout_seconds == 30
        assert config.webhook_retry_attempts == 3
        assert config.max_requests_per_minute == 100
        assert config.active is True

    def test_webhook_configuration_validators(self):
        """Verify that field validators work correctly."""
        enterprise = EnterpriseCustomerFactory()

        # Test timeout min/max
        with pytest.raises(ValidationError):
            config = EnterpriseWebhookConfiguration(
                enterprise_customer=enterprise,
                region='US',
                webhook_url='https://example.com/webhook',
                webhook_timeout_seconds=3  # Below min of 5
            )
            config.full_clean()

        with pytest.raises(ValidationError):
            config = EnterpriseWebhookConfiguration(
                enterprise_customer=enterprise,
                region='US',
                webhook_url='https://example.com/webhook',
                webhook_timeout_seconds=400  # Above max of 300
            )
            config.full_clean()

    def test_queue_item_status_choices(self):
        """Verify that valid status values work correctly."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')

        valid_statuses = ['pending', 'processing', 'success', 'failed', 'cancelled']

        for status in valid_statuses:
            item = WebhookTransmissionQueue.objects.create(
                enterprise_customer=enterprise,
                user=user,
                course_id=f'course-{status}',
                event_type='course_completion',
                user_region='US',
                webhook_url='https://example.com/webhook',
                payload={'event': 'test'},
                deduplication_key=f'key-{status}',
                status=status
            )
            assert item.status == status

    @freeze_time("2026-01-08 12:00:00")
    def test_queue_timestamps(self):
        """Verify that timestamps are set correctly."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')

        item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='course-id',
            event_type='course_completion',
            user_region='US',
            webhook_url='https://example.com/webhook',
            payload={'event': 'test'},
            deduplication_key='timestamp-key'
        )

        assert item.created is not None
        assert item.modified is not None
        assert item.last_attempt_at is None
        assert item.completed_at is None
        assert item.next_retry_at is None

    def test_multiple_enterprises_same_region(self):
        """Verify that different enterprises can have same region configs."""
        enterprise1 = EnterpriseCustomerFactory()
        enterprise2 = EnterpriseCustomerFactory()

        config1 = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise1,
            region='US',
            webhook_url='https://enterprise1.example.com/webhook'
        )

        # Different enterprise with same region should work
        config2 = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise2,
            region='US',
            webhook_url='https://enterprise2.example.com/webhook'
        )

        assert config1.id != config2.id
        assert config1.region == config2.region


@pytest.mark.django_db
class TestWebhookIntegration:
    """Integration tests for the full webhook flow."""

    def test_end_to_end_webhook_flow(self):
        """Test the complete flow from configuration to queue creation."""
        # Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='integration-user', email='int@example.com')

        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://integration.example.com/webhook',
            webhook_timeout_seconds=45,
            webhook_retry_attempts=5
        )

        # Execute
        payload = {
            'event': 'test',
            'timestamp': timezone.now().isoformat(),
            'data': {'key': 'value'}
        }

        with patch(
            'channel_integrations.integrated_channel.services.webhook_routing.get_user_region',
            return_value='US'
        ):
            queue_item, created = route_webhook_by_region(
                user=user,
                enterprise_customer=enterprise,
                course_id='course-v1:Test+Course+2026',
                event_type='course_completion',
                payload=payload
            )

        # Verify
        assert queue_item is not None
        assert created is True
        assert queue_item.enterprise_customer == enterprise
        assert queue_item.user == user
        assert queue_item.webhook_url == config.webhook_url
        assert queue_item.status == 'pending'
        assert queue_item.payload == payload
        assert queue_item.user_region == 'US'

        # Verify it's in the database
        retrieved = WebhookTransmissionQueue.objects.get(id=queue_item.id)
        assert retrieved.deduplication_key is not None

    def test_webhook_config_cascade_delete(self):
        """Verify that deleting enterprise customer cascades to webhook configs."""
        enterprise = EnterpriseCustomerFactory()

        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://example.com/webhook'
        )

        config_id = config.id

        # Delete enterprise customer
        enterprise.delete()

        # Webhook config should be deleted
        assert not EnterpriseWebhookConfiguration.objects.filter(id=config_id).exists()
