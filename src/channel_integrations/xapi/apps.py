"""
Enterprise xAPI Django application initialization.
"""

from django.apps import AppConfig


class XAPIConfig(AppConfig):
    """
    Configuration for the xAPI Django application.
    """
    name = 'channel_integrations.xapi'
    verbose_name = "Enterprise xAPI Integration (Experimental)"
    label = 'xapi_channel'
