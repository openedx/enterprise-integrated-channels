"""
Enterprise Integrated Channel Degreed Django application initialization.
"""

from django.apps import AppConfig


class DegreedConfig(AppConfig):
    """
    Configuration for the Enterprise Integrated Channel Degreed Django application.
    """
    name = 'channel_integrations.degreed'
    verbose_name = "Enterprise Degreed Integration"
    label = 'degreed_channel'
