"""
Test the Enterprise Integrated Channel tasks and related functions.
"""

import unittest
from unittest.mock import Mock, patch

import ddt
import pytest
from django.contrib.auth import get_user_model

from channel_integrations.integrated_channel.tasks import (
    enrich_and_send_completion_webhook,
    locked,
    unlink_inactive_learners,
)
from test_utils.factories import EnterpriseCustomerFactory, EnterpriseCustomerUserFactory

EXPIRY_SECONDS = 100
A_MOCK = Mock()


@locked(expiry_seconds=EXPIRY_SECONDS, lock_name_kwargs=['channel_code', 'channel_pk'])
def a_locked_method(username, channel_code, channel_pk):  # lint-amnesty, pylint: disable=unused-argument
    A_MOCK.subtask()


@locked(expiry_seconds=EXPIRY_SECONDS, lock_name_kwargs=['channel_code', 'channel_pk'])
def a_locked_method_exception(username, channel_code, channel_pk):
    raise Exception('a_locked_method_exception raised an Exception')


@ddt.ddt
class LockedTest(unittest.TestCase):
    """Test class to verify locking of mocked resources"""

    def setUp(self):
        super().setUp()
        A_MOCK.reset_mock()

    @patch('channel_integrations.integrated_channel.tasks.cache.delete')
    @patch('channel_integrations.integrated_channel.tasks.cache.add')
    @ddt.data(True, False)
    def test_locked_method(self, lock_available, add_mock, delete_mock):
        """
        Test that a method gets executed or not based on if a lock can be acquired
        """
        add_mock.return_value = lock_available
        username = 'edx_worker'
        channel_code = 'DEGREED2'
        channel_pk = 10
        a_locked_method(username=username, channel_code=channel_code, channel_pk=channel_pk)
        cache_key = f'a_locked_method-channel_code:{channel_code}-channel_pk:{channel_pk}'
        self.assertEqual(lock_available, A_MOCK.subtask.called)
        if lock_available:
            add_mock.assert_called_once_with(cache_key, "true", EXPIRY_SECONDS)
            delete_mock.assert_called_once()

    @patch('channel_integrations.integrated_channel.tasks.cache.delete')
    @patch('channel_integrations.integrated_channel.tasks.cache.add')
    def test_locked_method_exception(self, add_mock, delete_mock):
        """
        Test that a lock is unlocked when an exception is raised and that the exception is re-raised
        """
        lock_available = True
        add_mock.return_value = lock_available
        username = 'edx_worker'
        channel_code = 'DEGREED2'
        channel_pk = 10
        with pytest.raises(Exception):
            a_locked_method_exception(username=username, channel_code=channel_code, channel_pk=channel_pk)
        cache_key = f'a_locked_method_exception-channel_code:{channel_code}-channel_pk:{channel_pk}'
        add_mock.assert_called_once_with(cache_key, "true", EXPIRY_SECONDS)
        delete_mock.assert_called_once()


@pytest.mark.django_db
class TestUnlinkInactiveLearnersTask:
    """Tests for unlink_inactive_learners task."""

    @patch('channel_integrations.integrated_channel.tasks.INTEGRATED_CHANNEL_CHOICES')
    @patch('channel_integrations.integrated_channel.tasks._log_batch_task_finish')
    @patch('channel_integrations.integrated_channel.tasks._log_batch_task_start')
    def test_unlink_inactive_learners_logs_finish(
        self, mock_log_start, mock_log_finish, mock_choices  # pylint: disable=unused-argument
    ):
        """Test that unlink_inactive_learners task logs finish correctly."""
        # Create a mock integrated channel
        mock_channel = Mock()
        mock_channel.unlink_inactive_learners = Mock()
        mock_channel_class = Mock()
        mock_channel_class.objects.get.return_value = mock_channel
        mock_choices.__getitem__.return_value = mock_channel_class

        channel_code = 'TEST'
        channel_pk = 1

        # Execute the task
        unlink_inactive_learners(channel_code=channel_code, channel_pk=channel_pk)

        # Verify _log_batch_task_finish was called
        assert mock_log_finish.called
        call_args = mock_log_finish.call_args[0]
        assert call_args[0] == 'unlink_inactive_learners'
        assert call_args[1] == channel_code


@pytest.mark.django_db
class TestEnrichAndSendCompletionWebhookTask:
    """Tests for enrich_and_send_completion_webhook task."""

    @patch('channel_integrations.integrated_channel.tasks.process_webhook_queue')
    @patch('channel_integrations.integrated_channel.tasks.route_webhook_by_region')
    @patch('channel_integrations.integrated_channel.tasks.SnowflakeLearningTimeClient')
    def test_enrich_and_send_triggers_webhook_task_when_created(
        self, mock_snowflake, mock_route, mock_webhook_task
    ):
        """Test that enrich_and_send_completion_webhook triggers webhook task when created=True."""
        User = get_user_model()

        # Setup test data
        enterprise = EnterpriseCustomerFactory()
        user = User.objects.create(username='testuser', email='test@example.com')
        EnterpriseCustomerUserFactory(enterprise_customer=enterprise, user_id=user.id)

        course_id = 'course-v1:edX+DemoX+Demo'

        # Mock Snowflake client
        mock_client = mock_snowflake.return_value
        mock_client.get_learning_time.return_value = 1800

        # Mock routing to return tuple with created=True
        mock_queue_item = Mock(id=456)
        mock_route.return_value = (mock_queue_item, True)

        payload = {
            'completion': {
                'percent_grade': 0.88,
            }
        }

        with patch('channel_integrations.integrated_channel.tasks.settings') as mock_settings:
            mock_settings.FEATURES = {'ENABLE_WEBHOOK_LEARNING_TIME_ENRICHMENT': True}

            # Execute the task
            enrich_and_send_completion_webhook(
                user_id=user.id,
                course_id=course_id,
                enterprise_customer_uuid=str(enterprise.uuid),
                payload_dict=payload
            )

        # Verify the webhook task was triggered with the queue item ID
        mock_webhook_task.delay.assert_called_once_with(456)
