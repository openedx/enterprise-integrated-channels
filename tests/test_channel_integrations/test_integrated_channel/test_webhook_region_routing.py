"""
Integration tests for webhook region routing edge cases.

Tests complex routing scenarios including:
- Users without SSO metadata
- Inactive region configs with fallback
- Multiple enterprise customers
- Region fallback logic
"""
import pytest
import responses
from django.contrib.auth import get_user_model
from django.utils import timezone
from opaque_keys.edx.keys import CourseKey
from openedx_events.learning.data import CourseData, PersistentCourseGradeData
from social_django.models import UserSocialAuth

from channel_integrations.integrated_channel.handlers import handle_grade_change_for_webhooks
from channel_integrations.integrated_channel.models import EnterpriseWebhookConfiguration, WebhookTransmissionQueue
from test_utils.factories import EnterpriseCustomerFactory, EnterpriseCustomerUserFactory

User = get_user_model()


@pytest.mark.django_db
class TestWebhookRegionRoutingEdgeCases:
    """Test edge cases in webhook region routing logic."""

    @responses.activate
    def test_user_without_sso_uses_other_region(self):
        """Verify users without SSO metadata are routed to OTHER region."""
        # Setup - explicitly set country=None to avoid Priority #3 region detection
        enterprise = EnterpriseCustomerFactory(country=None)
        user = User.objects.create(username='no-sso-user', email='nosso@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        # No SSO metadata for user (no UserSocialAuth created)

        # Only OTHER region configured
        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='OTHER',
            webhook_url='https://other.example.com/webhook',
            active=True
        )

        # Mock HTTP endpoint
        responses.add(
            responses.POST,
            config.webhook_url,
            json={'status': 'ok'},
            status=200
        )

        # Create grade event
        course_key = CourseKey.from_string('course-v1:edX+NoSSO+2024')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='No SSO Course'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash123',
            percent_grade=0.88,
            letter_grade='B+',
            passed_timestamp=timezone.now()
        )

        # Invoke handler
        handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

        # Verify routed to OTHER region
        queue_item = WebhookTransmissionQueue.objects.get(user=user)
        assert queue_item.user_region == 'OTHER'
        assert queue_item.webhook_url == config.webhook_url
        assert queue_item.status == 'success'  # Celery ran eagerly

        # Verify HTTP call was made
        assert len(responses.calls) == 1

    @responses.activate
    def test_region_specific_config_inactive_uses_other_fallback(self):
        """Test that inactive region configs fall back to OTHER region."""

        # Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='eu-user', email='eu@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        # User has EU region in SSO
        UserSocialAuth.objects.create(
            user=user,
            provider='tpa-saml',
            uid='eu-uid',
            extra_data={'country': 'DE'}  # Maps to EU
        )

        # EU config exists but is INACTIVE
        EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='EU',
            webhook_url='https://eu-inactive.example.com/webhook',
            active=False  # INACTIVE
        )

        # OTHER region config is active (fallback)
        other_config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='OTHER',
            webhook_url='https://other-fallback.example.com/webhook',
            active=True
        )

        # Mock HTTP endpoint for OTHER
        responses.add(
            responses.POST,
            other_config.webhook_url,
            json={'fallback': True},
            status=200
        )

        # Create grade event
        course_key = CourseKey.from_string('course-v1:edX+Fallback+2024')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Fallback Course'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash456',
            percent_grade=0.92,
            letter_grade='A-',
            passed_timestamp=timezone.now()
        )

        # Invoke handler
        handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

        # Verify fell back to OTHER region
        queue_item = WebhookTransmissionQueue.objects.get(user=user)
        assert queue_item.user_region == 'EU'  # User's actual region
        assert queue_item.webhook_url == other_config.webhook_url  # But OTHER config used
        assert queue_item.status == 'success'

        # Verify HTTP call went to fallback
        assert len(responses.calls) == 1
        assert responses.calls[0].request.url == other_config.webhook_url

    @responses.activate
    def test_multi_enterprise_user_sends_multiple_webhooks(self):
        """Verify user in multiple enterprises sends webhooks to all."""

        # User belongs to 2 enterprises
        user = User.objects.create(username='multi-enterprise', email='multi@example.com')

        enterprise1 = EnterpriseCustomerFactory(name='Enterprise 1')
        enterprise2 = EnterpriseCustomerFactory(name='Enterprise 2')

        EnterpriseCustomerUserFactory(enterprise_customer=enterprise1, user_id=user.id)
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise2, user_id=user.id)

        # User has US region
        UserSocialAuth.objects.create(
            user=user,
            provider='tpa-saml',
            uid='multi-uid',
            extra_data={'country': 'US'}
        )

        # Each enterprise has different webhook
        config1 = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise1,
            region='US',
            webhook_url='https://enterprise1.example.com/webhook',
            active=True
        )

        config2 = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise2,
            region='US',
            webhook_url='https://enterprise2.example.com/webhook',
            active=True
        )

        # Mock both endpoints
        responses.add(
            responses.POST,
            config1.webhook_url,
            json={'enterprise': 1},
            status=200
        )
        responses.add(
            responses.POST,
            config2.webhook_url,
            json={'enterprise': 2},
            status=200
        )

        # Create grade event
        course_key = CourseKey.from_string('course-v1:edX+Multi+2024')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Multi Enterprise Course'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash789',
            percent_grade=0.95,
            letter_grade='A',
            passed_timestamp=timezone.now()
        )

        # Invoke handler
        handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

        # Verify TWO queue items created (one per enterprise)
        queue_items = WebhookTransmissionQueue.objects.filter(user=user).order_by('webhook_url')
        assert queue_items.count() == 2

        # Verify each went to correct webhook
        assert queue_items[0].webhook_url == config1.webhook_url
        assert queue_items[0].enterprise_customer == enterprise1
        assert queue_items[0].status == 'success'

        assert queue_items[1].webhook_url == config2.webhook_url
        assert queue_items[1].enterprise_customer == enterprise2
        assert queue_items[1].status == 'success'

        # Verify HTTP calls to BOTH endpoints
        assert len(responses.calls) == 2
        urls_called = {call.request.url for call in responses.calls}
        assert config1.webhook_url in urls_called
        assert config2.webhook_url in urls_called

    @responses.activate
    def test_deduplication_prevents_duplicate_webhooks_same_day(self):
        """Verify deduplication prevents duplicate webhooks for same event on same day."""

        # Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='dedup-user', email='dedup@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        UserSocialAuth.objects.create(
            user=user,
            provider='tpa-saml',
            uid='dedup-uid',
            extra_data={'country': 'US'}
        )

        config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://dedup.example.com/webhook',
            active=True
        )

        # Mock endpoint
        responses.add(
            responses.POST,
            config.webhook_url,
            json={'ok': True},
            status=200
        )

        # Create grade event
        course_key = CourseKey.from_string('course-v1:edX+Dedup+2024')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Dedup Course'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash111',
            percent_grade=0.85,
            letter_grade='B',
            passed_timestamp=timezone.now()
        )

        # Invoke handler TWICE with same event
        handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)
        handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

        # Verify only ONE queue item created (deduplication worked)
        queue_items = WebhookTransmissionQueue.objects.filter(user=user)
        assert queue_items.count() == 1

        # Verify only ONE HTTP call made
        assert len(responses.calls) == 1

    @responses.activate
    def test_explicit_region_in_sso_overrides_country_mapping(self):
        """Test that explicit 'region' in SSO data takes precedence over country mapping."""

        # Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='explicit-region', email='explicit@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        # User has BOTH explicit region AND country in SSO
        # Explicit region should take precedence
        UserSocialAuth.objects.create(
            user=user,
            provider='tpa-saml',
            uid='explicit-uid',
            extra_data={
                'region': 'UK',  # Explicit region (Priority #1)
                'country': 'US'  # Country that would map to US (Priority #2)
            }
        )

        # UK config
        uk_config = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='UK',
            webhook_url='https://uk.example.com/webhook',
            active=True
        )

        # US config also exists
        EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region='US',
            webhook_url='https://us-wrong.example.com/webhook',
            active=True
        )

        # Mock UK endpoint
        responses.add(
            responses.POST,
            uk_config.webhook_url,
            json={'region': 'UK'},
            status=200
        )

        # Create grade event
        course_key = CourseKey.from_string('course-v1:edX+Explicit+2024')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='Explicit Region Course'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash222',
            percent_grade=0.90,
            letter_grade='A-',
            passed_timestamp=timezone.now()
        )

        # Invoke handler
        handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

        # Verify routed to UK (explicit region) not US (country)
        queue_item = WebhookTransmissionQueue.objects.get(user=user)
        assert queue_item.user_region == 'UK'
        assert queue_item.webhook_url == uk_config.webhook_url
        assert queue_item.status == 'success'

        # Verify HTTP call went to UK endpoint
        assert len(responses.calls) == 1
        assert responses.calls[0].request.url == uk_config.webhook_url

    @responses.activate
    def test_no_webhook_config_for_region_no_other_fallback_skips_queue(self):
        """Test that events are skipped when no webhook config exists for region."""

        # Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='no-config', email='noconfig@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        # User has EU region
        UserSocialAuth.objects.create(
            user=user,
            provider='tpa-saml',
            uid='no-config-uid',
            extra_data={'country': 'FR'}  # Maps to EU
        )

        # NO webhook configs at all for this enterprise

        # Create grade event
        course_key = CourseKey.from_string('course-v1:edX+NoConfig+2024')
        grade_data = PersistentCourseGradeData(
            user_id=user.id,
            course=CourseData(course_key=course_key, display_name='No Config Course'),
            course_edited_timestamp=timezone.now(),
            course_version='1',
            grading_policy_hash='hash333',
            percent_grade=0.87,
            letter_grade='B+',
            passed_timestamp=timezone.now()
        )

        # Invoke handler
        handle_grade_change_for_webhooks(sender=None, signal=None, grade=grade_data)

        # Verify NO queue item created (no config available)
        queue_items = WebhookTransmissionQueue.objects.filter(user=user)
        assert queue_items.count() == 0

        # Verify NO HTTP calls made
        assert len(responses.calls) == 0
