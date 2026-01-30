"""
Integration tests for webhook learning time enrichment.

These tests verify the end-to-end flow of enriching webhook payloads with learning time data.
"""
# pylint: disable=import-outside-toplevel
import logging
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from waffle.testutils import override_switch

from test_utils.factories import EnterpriseCustomerFactory, EnterpriseCustomerUserFactory

User = get_user_model()
logger = logging.getLogger(__name__)


@pytest.mark.django_db
class TestWebhookLearningTimeIntegration:
    """Integration tests for the complete learning time enrichment flow."""

    @patch('channel_integrations.integrated_channel.tasks.SnowflakeLearningTimeClient')
    @patch('channel_integrations.integrated_channel.tasks.route_webhook_by_region')
    @override_switch('enable_webhook_learning_time_enrichment', active=True)
    def test_enrichment_task_adds_learning_time_to_payload(self, mock_route, mock_snowflake_class):
        """
        Test that the enrichment task correctly adds learning_time to the completion payload.

        This is the core integration test - it verifies:
        1. Task can query Snowflake client
        2. Learning time is added to payload['completion']['learning_time']
        3. Webhook is routed with enriched payload
        """
        from channel_integrations.integrated_channel.tasks import enrich_and_send_completion_webhook

        # Setup test data
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_id = 'course-v1:edX+DemoX+Demo_Course'

        # Mock Snowflake to return learning time
        mock_client = Mock()
        mock_client.get_learning_time.return_value = 3600  # 1 hour
        mock_snowflake_class.return_value = mock_client

        # Create initial payload (as created by handler)
        payload = {
            'completion': {
                'percent_grade': 0.90,
                'letter_grade': 'A',
            },
            'course': {
                'course_key': course_id,
            }
        }

        # Mock routing to return success
        mock_route.return_value = (Mock(id=1), True)

        # Execute enrichment task
        enrich_and_send_completion_webhook(
            user_id=user.id,
            course_id=course_id,
            enterprise_customer_uuid=str(enterprise.uuid),
            payload_dict=payload
        )

        # Verify Snowflake was queried
        mock_client.get_learning_time.assert_called_once_with(
            user_id=user.id,
            course_id=course_id,
            enterprise_customer_uuid=str(enterprise.uuid)
        )

        # Verify webhook was routed with enriched payload
        mock_route.assert_called_once()
        call_kwargs = mock_route.call_args[1]

        enriched_payload = call_kwargs['payload']
        assert 'completion' in enriched_payload
        assert 'learning_time' in enriched_payload['completion']
        assert enriched_payload['completion']['learning_time'] == 3600
        assert enriched_payload['completion']['percent_grade'] == 0.90

    @patch('channel_integrations.integrated_channel.tasks.SnowflakeLearningTimeClient')
    @patch('channel_integrations.integrated_channel.tasks.route_webhook_by_region')
    @override_switch('enable_webhook_learning_time_enrichment', active=True)
    def test_graceful_degradation_when_snowflake_fails(self, mock_route, mock_snowflake_class):
        """
        Test that webhook is still sent if Snowflake query fails.

        This verifies graceful degradation - enrichment failure should not break the webhook.
        """
        from channel_integrations.integrated_channel.tasks import enrich_and_send_completion_webhook

        # Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_id = 'course-v1:edX+DemoX+Demo_Course'

        # Mock Snowflake to raise exception
        mock_snowflake_class.side_effect = Exception("Connection failed")

        # Mock routing to return success
        mock_route.return_value = (Mock(id=1), True)

        payload = {
            'completion': {
                'percent_grade': 0.85,
            },
        }

        # Execute task - should NOT raise exception
        enrich_and_send_completion_webhook(
            user_id=user.id,
            course_id=course_id,
            enterprise_customer_uuid=str(enterprise.uuid),
            payload_dict=payload
        )

        # Verify webhook was still sent (without learning_time)
        mock_route.assert_called_once()
        call_kwargs = mock_route.call_args[1]

        sent_payload = call_kwargs['payload']
        assert 'completion' in sent_payload
        # learning_time should NOT be present due to error
        assert 'learning_time' not in sent_payload['completion']
        assert sent_payload['completion']['percent_grade'] == 0.85

    @patch('channel_integrations.integrated_channel.tasks.SnowflakeLearningTimeClient')
    @patch('channel_integrations.integrated_channel.tasks.route_webhook_by_region')
    @override_switch('enable_webhook_learning_time_enrichment', active=True)
    def test_no_learning_time_when_snowflake_returns_none(self, mock_route, mock_snowflake_class):
        """
        Test that webhook is sent without learning_time if Snowflake returns None.

        None means no data available for this user/course.
        """
        from channel_integrations.integrated_channel.tasks import enrich_and_send_completion_webhook

        # Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_id = 'course-v1:edX+DemoX+Demo_Course'

        # Mock Snowflake to return None (no data)
        mock_client = Mock()
        mock_client.get_learning_time.return_value = None
        mock_snowflake_class.return_value = mock_client

        # Mock routing to return success
        mock_route.return_value = (Mock(id=1), True)

        payload = {
            'completion': {
                'percent_grade': 0.75,
            },
        }

        # Execute task
        enrich_and_send_completion_webhook(
            user_id=user.id,
            course_id=course_id,
            enterprise_customer_uuid=str(enterprise.uuid),
            payload_dict=payload
        )

        # Verify webhook was sent without learning_time
        mock_route.assert_called_once()
        call_kwargs = mock_route.call_args[1]

        sent_payload = call_kwargs['payload']
        assert 'completion' in sent_payload
        # learning_time should NOT be added when value is None
        assert 'learning_time' not in sent_payload['completion']

    @patch('channel_integrations.integrated_channel.tasks.SnowflakeLearningTimeClient')
    @patch('channel_integrations.integrated_channel.tasks.route_webhook_by_region')
    @override_switch('enable_webhook_learning_time_enrichment', active=True)
    def test_zero_learning_time_is_added_to_payload(self, mock_route, mock_snowflake_class):
        """
        Test that learning_time=0 is correctly included in the payload.

        Zero is a valid value and should not be treated as "no data".
        """
        from channel_integrations.integrated_channel.tasks import enrich_and_send_completion_webhook

        # Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_id = 'course-v1:edX+DemoX+Demo_Course'

        # Mock Snowflake to return 0
        mock_client = Mock()
        mock_client.get_learning_time.return_value = 0
        mock_snowflake_class.return_value = mock_client

        # Mock routing to return success
        mock_route.return_value = (Mock(id=1), True)

        payload = {
            'completion': {
                'percent_grade': 1.0,
            },
        }

        # Execute task
        enrich_and_send_completion_webhook(
            user_id=user.id,
            course_id=course_id,
            enterprise_customer_uuid=str(enterprise.uuid),
            payload_dict=payload
        )

        # Verify webhook was sent with learning_time=0
        mock_route.assert_called_once()
        call_kwargs = mock_route.call_args[1]

        sent_payload = call_kwargs['payload']
        assert 'completion' in sent_payload
        assert 'learning_time' in sent_payload['completion']
        assert sent_payload['completion']['learning_time'] == 0

    @patch('channel_integrations.integrated_channel.tasks.route_webhook_by_region')
    @override_switch('enable_webhook_learning_time_enrichment', active=False)
    def test_feature_flag_disabled_no_enrichment(self, mock_route):
        """
        Test that with feature flag OFF, no enrichment occurs.

        This is the backward-compatible default behavior.
        """
        from channel_integrations.integrated_channel.tasks import enrich_and_send_completion_webhook

        # Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_id = 'course-v1:edX+DemoX+Demo_Course'

        # Mock routing to return success
        mock_route.return_value = (Mock(id=1), True)

        payload = {
            'completion': {
                'percent_grade': 0.92,
            },
        }

        # Execute task with feature flag OFF
        enrich_and_send_completion_webhook(
            user_id=user.id,
            course_id=course_id,
            enterprise_customer_uuid=str(enterprise.uuid),
            payload_dict=payload
        )

        # Verify webhook was routed without enrichment attempt
        mock_route.assert_called_once()
        call_kwargs = mock_route.call_args[1]

        sent_payload = call_kwargs['payload']
        assert 'learning_time' not in sent_payload.get('completion', {})
        assert sent_payload['completion']['percent_grade'] == 0.92

    @patch('channel_integrations.integrated_channel.tasks.SnowflakeLearningTimeClient')
    @patch('channel_integrations.integrated_channel.tasks.route_webhook_by_region')
    @override_switch('enable_webhook_learning_time_enrichment', active=True)
    def test_enrichment_creates_completion_section_if_missing(self, mock_route, mock_snowflake_class):
        """
        Test that enrichment creates the completion section if it doesn't exist.

        This covers line 523 in tasks.py where we create payload['completion'] if missing.
        """
        from channel_integrations.integrated_channel.tasks import enrich_and_send_completion_webhook

        # Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_id = 'course-v1:edX+DemoX+Demo_Course'

        # Mock Snowflake to return learning time
        mock_client = Mock()
        mock_client.get_learning_time.return_value = 5400  # 1.5 hours
        mock_snowflake_class.return_value = mock_client

        # Mock routing to return success
        mock_route.return_value = (Mock(id=1), True)

        # Create payload WITHOUT completion section
        payload = {
            'course': {
                'course_key': course_id,
            }
        }

        # Execute enrichment task
        enrich_and_send_completion_webhook(
            user_id=user.id,
            course_id=course_id,
            enterprise_customer_uuid=str(enterprise.uuid),
            payload_dict=payload
        )

        # Verify completion section was created with learning_time
        mock_route.assert_called_once()
        call_kwargs = mock_route.call_args[1]

        enriched_payload = call_kwargs['payload']
        assert 'completion' in enriched_payload
        assert enriched_payload['completion']['learning_time'] == 5400

    @patch('channel_integrations.integrated_channel.tasks.SnowflakeLearningTimeClient')
    @patch('channel_integrations.integrated_channel.tasks.route_webhook_by_region')
    @override_switch('enable_webhook_learning_time_enrichment', active=True)
    def test_routing_exception_is_raised(self, mock_route, mock_snowflake_class):
        """
        Test that routing exceptions are properly raised.

        This covers lines 565-571 in tasks.py where routing exceptions are caught and raised.
        """
        from channel_integrations.integrated_channel.tasks import enrich_and_send_completion_webhook

        # Setup
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_id = 'course-v1:edX+DemoX+Demo_Course'

        # Mock Snowflake to return learning time
        mock_client = Mock()
        mock_client.get_learning_time.return_value = 1800
        mock_snowflake_class.return_value = mock_client

        # Mock routing to raise an exception
        mock_route.side_effect = Exception("Routing failed")

        payload = {
            'completion': {
                'percent_grade': 0.85,
            },
        }

        # Execute task - should raise the routing exception
        with pytest.raises(Exception, match="Routing failed"):
            enrich_and_send_completion_webhook(
                user_id=user.id,
                course_id=course_id,
                enterprise_customer_uuid=str(enterprise.uuid),
                payload_dict=payload
            )
