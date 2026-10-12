"""
Signal receivers for Enterprise Integrated Channels.

This module connects OpenEdX Events signals directly to handlers,
bypassing the event bus to avoid serialization issues.
"""
from django.dispatch import receiver
from openedx_events.learning.signals import (
    COURSE_ENROLLMENT_CREATED,
    PERSISTENT_GRADE_SUMMARY_CHANGED,
)

from channel_integrations.integrated_channel import handlers


@receiver(PERSISTENT_GRADE_SUMMARY_CHANGED)
def handle_grade_change_signal(sender, signal=None, **kwargs):
    """
    Signal receiver for grade changes.

    Connects the in-process signal directly to the handler.
    """
    handlers.handle_grade_change_for_webhooks(sender, signal, **kwargs)


@receiver(COURSE_ENROLLMENT_CREATED)
def handle_enrollment_created_signal(sender, signal=None, **kwargs):
    """
    Signal receiver for enrollment creation.

    Connects the in-process signal directly to the handler.
    """
    handlers.handle_enrollment_for_webhooks(sender, signal, **kwargs)
