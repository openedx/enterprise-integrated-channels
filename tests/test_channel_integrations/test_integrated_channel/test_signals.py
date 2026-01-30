"""
Tests for signal connections in Enterprise Integrated Channels.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase
from openedx_events.learning.signals import COURSE_ENROLLMENT_CREATED, PERSISTENT_GRADE_SUMMARY_CHANGED

# Explicitly import signals to ensure receivers are registered
from channel_integrations.integrated_channel import signals


class TestSignalConnections(TestCase):
    """
    Tests to verify signals are properly connected to handlers.
    """

    def test_grade_change_signal_has_receivers(self):
        """
        Test that PERSISTENT_GRADE_SUMMARY_CHANGED has receivers registered.
        """
        # Check that at least one receiver is registered
        # pylint: disable=protected-access
        receivers = PERSISTENT_GRADE_SUMMARY_CHANGED._live_receivers(None)
        self.assertGreater(
            len(receivers), 0,
            "PERSISTENT_GRADE_SUMMARY_CHANGED should have at least one receiver")

        # Check that our specific receiver is in the list
        receiver_names = [r.__name__ if hasattr(r, '__name__') else str(r) for r in receivers]
        self.assertIn(
            'handle_grade_change_signal', str(receiver_names),
            "handle_grade_change_signal should be registered as a receiver")

    def test_enrollment_signal_has_receivers(self):
        """
        Test that COURSE_ENROLLMENT_CREATED has receivers registered.
        """
        # Check that at least one receiver is registered
        # pylint: disable=protected-access
        receivers = COURSE_ENROLLMENT_CREATED._live_receivers(None)
        self.assertGreater(
            len(receivers), 0,
            "COURSE_ENROLLMENT_CREATED should have at least one receiver")

        # Check that our specific receiver is in the list
        receiver_names = [r.__name__ if hasattr(r, '__name__') else str(r) for r in receivers]
        self.assertIn(
            'handle_enrollment_created_signal', str(receiver_names),
            "handle_enrollment_created_signal should be registered as a receiver")

    @patch('channel_integrations.integrated_channel.handlers.handle_grade_change_for_webhooks')
    def test_grade_signal_receiver_logic(self, mock_handler):
        """
        Unit test: verify receiver calls handler.
        This achieves coverage of signals.py line 23.
        """
        grade_data = MagicMock()

        # Call the receiver function directly
        signals.handle_grade_change_signal(
            sender=None,
            grade=grade_data
        )

        # Verify the handler was called
        mock_handler.assert_called_once()
        call_kwargs = mock_handler.call_args[1]
        self.assertEqual(call_kwargs['grade'], grade_data)

    @patch('channel_integrations.integrated_channel.handlers.handle_enrollment_for_webhooks')
    def test_enrollment_signal_receiver_logic(self, mock_handler):
        """
        Unit test: verify receiver calls handler.
        This achieves coverage of signals.py line 33.
        """
        enrollment_data = MagicMock()

        # Call the receiver function directly
        signals.handle_enrollment_created_signal(
            sender=None,
            enrollment=enrollment_data
        )

        # Verify the handler was called
        mock_handler.assert_called_once()
        call_kwargs = mock_handler.call_args[1]
        self.assertEqual(call_kwargs['enrollment'], enrollment_data)
