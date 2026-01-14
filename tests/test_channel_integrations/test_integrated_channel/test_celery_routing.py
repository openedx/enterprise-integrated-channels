"""
Tests for Celery task routing configuration.
"""
from unittest.mock import patch

import pytest
from django.conf import settings


@pytest.mark.django_db
class TestCeleryTaskRouting:
    """Tests to verify Celery task routing configuration."""

    def test_enrichment_task_has_queue_route(self):
        """
        Verify that the enrichment task has a queue route configured.
        
        This ensures the task will be routed to the dedicated webhook_enrichment queue.
        """
        task_name = 'channel_integrations.integrated_channel.tasks.enrich_and_send_completion_webhook'
        
        # Verify route exists in settings
        assert hasattr(settings, 'CELERY_TASK_ROUTES'), "CELERY_TASK_ROUTES not configured"
        assert task_name in settings.CELERY_TASK_ROUTES, f"{task_name} not in CELERY_TASK_ROUTES"
        
        # Verify queue name
        route = settings.CELERY_TASK_ROUTES[task_name]
        assert 'queue' in route, "Route missing 'queue' key"
        assert route['queue'] == 'edx.lms.core.webhook_enrichment', \
            f"Expected queue 'edx.lms.core.webhook_enrichment', got '{route['queue']}'"

    def test_enrichment_task_can_be_imported(self):
        """
        Verify the enrichment task can be imported successfully.
        
        This ensures the task is properly registered with Celery.
        """
        from channel_integrations.integrated_channel.tasks import enrich_and_send_completion_webhook
        
        assert enrich_and_send_completion_webhook is not None
        assert callable(enrich_and_send_completion_webhook)
        
        # Verify it's a Celery task
        assert hasattr(enrich_and_send_completion_webhook, 'delay'), \
            "Task missing 'delay' method - not a Celery task?"
        assert hasattr(enrich_and_send_completion_webhook, 'apply_async'), \
            "Task missing 'apply_async' method - not a Celery task?"

    @patch('channel_integrations.integrated_channel.tasks.SnowflakeLearningTimeClient')
    @patch('channel_integrations.integrated_channel.services.webhook_routing.route_webhook_by_region')
    def test_enrichment_task_execution_with_settings(self, mock_route, mock_snowflake):
        """
        Verify the enrichment task executes correctly with proper settings.
        
        This is an integration test ensuring the task works with the configured queue.
        """
        from channel_integrations.integrated_channel.tasks import enrich_and_send_completion_webhook
        from test_utils.factories import EnterpriseCustomerFactory, EnterpriseCustomerUserFactory
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        # Setup test data
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)
        
        course_id = 'course-v1:edX+DemoX+Demo'
        
        # Mock Snowflake
        mock_client = mock_snowflake.return_value
        mock_client.get_learning_time.return_value = 1800  # 30 minutes
        
        payload = {
            'completion': {
                'percent_grade': 0.88,
            }
        }
        
        # Execute task directly (not via queue, since we're in test mode)
        # In production, this would be: enrich_and_send_completion_webhook.delay(...)
        with patch('channel_integrations.integrated_channel.tasks.settings') as mock_settings:
            mock_settings.FEATURES = {'ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT': True}
            
            enrich_and_send_completion_webhook(
                user_id=user.id,
                course_id=course_id,
                enterprise_customer_uuid=str(enterprise.uuid),
                payload_dict=payload
            )
        
        # Verify webhook was routed
        mock_route.assert_called_once()
        
        # Verify learning_time was added
        call_kwargs = mock_route.call_args[1]
        enriched_payload = call_kwargs['payload']
        assert 'learning_time' in enriched_payload['completion']
        assert enriched_payload['completion']['learning_time'] == 1800

    def test_queue_configuration_values(self):
        """
        Verify the queue configuration uses appropriate values.
        
        This test documents the expected queue configuration.
        """
        route = settings.CELERY_TASK_ROUTES.get(
            'channel_integrations.integrated_channel.tasks.enrich_and_send_completion_webhook'
        )
        
        assert route is not None, "Task route not configured"
        
        # Document expected configuration
        expected_queue = 'edx.lms.core.webhook_enrichment'
        assert route['queue'] == expected_queue, \
            f"Queue should be '{expected_queue}' for proper resource isolation"
        
        # Verify no other routing options that might interfere
        # (e.g., we don't want routing_key, exchange overrides unless intentional)
        assert 'routing_key' not in route or route['routing_key'] == expected_queue, \
            "Unexpected routing_key configuration"
