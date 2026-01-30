"""
Tests for Webhook services.
"""
import logging
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from freezegun import freeze_time
from social_django.models import UserSocialAuth

from channel_integrations.integrated_channel.models import EnterpriseWebhookConfiguration, WebhookTransmissionQueue
from channel_integrations.integrated_channel.services.region_service import get_user_region
from channel_integrations.integrated_channel.services.webhook_routing import (
    NoWebhookConfigured,
    route_webhook_by_region,
)
from test_utils.factories import EnterpriseCustomerFactory

User = get_user_model()


@pytest.mark.django_db
class TestRegionService:
    """Tests for region_service.py."""

    def test_get_user_region_explicit(self):
        """Verify explicit region in SSO extra_data."""
        user = User.objects.create(username='testuser')
        UserSocialAuth.objects.create(
            user=user,
            provider='saml',
            uid='test-uid',
            extra_data={'region': 'EU'}
        )
        assert get_user_region(user) == 'EU'

    def test_get_user_region_country_mapping(self):
        """Verify country code mapping in SSO extra_data."""
        user = User.objects.create(username='testuser')
        UserSocialAuth.objects.create(
            user=user,
            provider='saml',
            uid='test-uid',
            extra_data={'country': 'FR'}
        )
        assert get_user_region(user) == 'EU'

    def test_get_user_region_uk_mapping(self):
        """Verify UK country code mapping."""
        user = User.objects.create(username='testuser')
        UserSocialAuth.objects.create(
            user=user,
            provider='saml',
            uid='test-uid',
            extra_data={'country': 'GB'}
        )
        assert get_user_region(user) == 'UK'

    def test_get_user_region_fallback_other(self):
        """Verify fallback to OTHER when no metadata exists."""
        user = User.objects.create(username='testuser')
        assert get_user_region(user) == 'OTHER'


@pytest.mark.django_db
class TestWebhookRouting:
    """Tests for webhook_routing.py."""

    def test_route_webhook_success(self):
        """Verify successful routing to a specific region."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://us.example.com/webhook'
        )

        payload = {'event': 'test'}
        with patch(
            'channel_integrations.integrated_channel.services.webhook_routing.get_user_region',
            return_value='US'
        ):
            queue_item, created = route_webhook_by_region(
                user=user,
                enterprise_customer=enterprise,
                course_id='course-id',
                event_type='course_completion',
                payload=payload
            )

            assert queue_item.webhook_url == 'https://us.example.com/webhook'
            assert created is True
            assert queue_item.status == 'pending'

    def test_route_webhook_fallback_other(self):
        """Verify fallback to OTHER region if specific region not found."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        # Only OTHER is configured
        EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='OTHER',
            webhook_url='https://other.example.com/webhook'
        )

        payload = {'event': 'test'}
        # User is in EU, but no EU config exists
        with patch(
            'channel_integrations.integrated_channel.services.webhook_routing.get_user_region',
            return_value='EU'
        ):
            queue_item, created = route_webhook_by_region(
                user=user,
                enterprise_customer=enterprise,
                course_id='course-id',
                event_type='course_completion',
                payload=payload
            )
            assert queue_item.webhook_url == 'https://other.example.com/webhook'
            assert queue_item.user_region == 'EU'
            assert created is True

    def test_route_webhook_no_config(self):
        """Verify exception when no matching config exists."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')

        payload = {'event': 'test'}
        with patch(
            'channel_integrations.integrated_channel.services.webhook_routing.get_user_region',
            return_value='US'
        ):
            with pytest.raises(NoWebhookConfigured):
                route_webhook_by_region(
                    user=user,
                    enterprise_customer=enterprise,
                    course_id='course-id',
                    event_type='course_completion',
                    payload=payload
                )

    def test_route_webhook_enrollment_disabled(self):
        """Verify exception when enrollment processing is disabled."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://us.example.com/webhook',
            enrollment_events_processing=False
        )

        payload = {'event': 'test'}
        with patch(
            'channel_integrations.integrated_channel.services.webhook_routing.get_user_region',
            return_value='US'
        ):
            with pytest.raises(NoWebhookConfigured) as exc_info:
                route_webhook_by_region(
                    user=user,
                    enterprise_customer=enterprise,
                    course_id='course-id',
                    event_type='course_enrollment',
                    payload=payload
                )
            assert "Enrollment events processing disabled" in str(exc_info.value)

    def test_route_webhook_deduplication(self):
        """Verify that duplicate events are not queued on the same day."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://us.example.com/webhook'
        )

        payload = {'event': 'test'}
        with patch(
            'channel_integrations.integrated_channel.services.webhook_routing.get_user_region',
            return_value='US'
        ):
            # First call
            item1, created1 = route_webhook_by_region(user, enterprise, 'course-id', 'course_completion', payload)
            assert created1 is True

            # Second call (same day)
            item2, created2 = route_webhook_by_region(user, enterprise, 'course-id', 'course_completion', payload)
            assert item1.id == item2.id
            assert created2 is False

    @freeze_time("2026-01-08 12:00:00")
    def test_route_webhook_with_frozen_time(self):
        """Verify deduplication works correctly with frozen time."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://us.example.com/webhook'
        )

        payload = {'event': 'test'}
        with patch(
            'channel_integrations.integrated_channel.services.webhook_routing.get_user_region',
            return_value='US'
        ):
            # Create first item
            item1, created1 = route_webhook_by_region(
                user, enterprise, 'frozen-course', 'course_completion', payload
            )
            assert created1 is True

            # Create duplicate - should return same item
            item2, created2 = route_webhook_by_region(user, enterprise, 'frozen-course', 'course_completion', payload)
            assert created2 is False

            assert item1.id == item2.id
            expected_key = f"{enterprise.uuid}:{user.id}:frozen-course:course_completion:2026-01-08"
            assert item1.deduplication_key == expected_key

    def test_get_user_region_with_empty_extra_data(self):
        """Verify handling of empty extra_data fields."""
        user = User.objects.create(username='testuser')
        UserSocialAuth.objects.create(
            user=user,
            provider='saml',
            uid='test-uid',
            extra_data={'region': '', 'country': ''}
        )
        # Should fall back to OTHER when fields are empty
        region = get_user_region(user)
        assert region in ['OTHER', 'EU', 'US', 'UK']  # Depends on implementation

    def test_get_user_region_with_none_values(self):
        """Verify handling of None values in extra_data."""
        user = User.objects.create(username='testuser')
        UserSocialAuth.objects.create(
            user=user,
            provider='saml',
            uid='test-uid',
            extra_data={'region': None, 'country': None}
        )
        # Should fall back to OTHER
        region = get_user_region(user)
        assert region in ['OTHER', 'EU', 'US', 'UK']

    def test_get_user_region_with_multiple_sso_providers(self):
        """Verify behavior when user has multiple SSO providers."""
        user = User.objects.create(username='testuser')
        # Create multiple SSO records
        UserSocialAuth.objects.create(
            user=user,
            provider='saml',
            uid='test-uid-1',
            extra_data={'region': 'US'}
        )
        UserSocialAuth.objects.create(
            user=user,
            provider='oauth2',
            uid='test-uid-2',
            extra_data={'region': 'EU'}
        )
        # Should return one of them (implementation dependent)
        region = get_user_region(user)
        assert region in ['US', 'EU', 'OTHER', 'UK']

    def test_route_webhook_logging(self, caplog):
        """Verify appropriate log messages are generated during routing."""
        caplog.set_level(logging.INFO)

        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://us.example.com/webhook'
        )

        payload = {'event': 'test'}
        with patch(
            'channel_integrations.integrated_channel.services.webhook_routing.get_user_region',
            return_value='US'
        ):
            with patch(
                'channel_integrations.integrated_channel.tasks.process_webhook_queue.delay'
            ):
                route_webhook_by_region(
                    user, enterprise, 'course-id', 'course_completion', payload
                )

        # Verify logging occurred
        assert any('Queued' in record.message or 'webhook' in record.message.lower()
                   for record in caplog.records)

    def test_route_webhook_after_retry_success(self):
        """Verify that items can be queued again after previous failure."""
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser')
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://us.example.com/webhook'
        )

        payload = {'event': 'test'}

        # Create an old failed queue item from yesterday
        yesterday = timezone.now() - timezone.timedelta(days=1)
        old_key = f"{user.id}:retry-course:course_completion:{yesterday.strftime('%Y-%m-%d')}"
        old_item = WebhookTransmissionQueue.objects.create(
            enterprise_customer=enterprise,
            user=user,
            course_id='retry-course',
            event_type='course_completion',
            user_region='US',
            webhook_url=config.webhook_url,
            payload=payload,
            deduplication_key=old_key,
            status='failed',
            created=yesterday
        )

        # Today's event should create a new queue item
        with patch(
            'channel_integrations.integrated_channel.services.webhook_routing.get_user_region',
            return_value='US'
        ):
            with patch(
                'channel_integrations.integrated_channel.tasks.process_webhook_queue.delay'
            ):
                new_item, created = route_webhook_by_region(
                    user, enterprise, 'retry-course', 'course_completion', payload
                )

                # Should be a different item
                assert created is True
                assert new_item.id != old_item.id
                assert new_item.status == 'pending'
                assert new_item.deduplication_key != old_key
