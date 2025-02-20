"""
Enterprise Integrated Channel Moodle Django application initialization.
"""

from django.apps import AppConfig


class MoodleConfig(AppConfig):
    """
    Configuration for the Enterprise Integrated Channel Moodle Django application.
    """
    name = 'channel_integrations.moodle'
    verbose_name = 'Enterprise Moodle Integration'
    label = 'moodle_channel'
