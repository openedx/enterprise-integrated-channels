"""
Enterprise Integrated Channel Cornerstone Django application initialization.
"""

from django.apps import AppConfig


class CornerstoneConfig(AppConfig):
    """
    Configuration for the Enterprise Integrated Channel Cornerstone Django application.
    """
    name = 'channel_integrations.cornerstone'
    verbose_name = "Enterprise Cornerstone Integration"
    label = 'cornerstone_channel'
