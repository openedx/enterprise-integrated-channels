"""
Enterprise Integrated Channel Django application initialization.
"""

from django.apps import AppConfig


class IntegratedChannelConfig(AppConfig):
    """
    Configuration for the Enterprise Integrated Channel Django application.
    """
    name = 'channel_integrations.integrated_channel'
    verbose_name = "Enterprise Integrated Channels (Experimental)"
    label = 'channel_integration'

    def ready(self):
        """
        Register signal handlers.
        """
        # pylint: disable=import-outside-toplevel, unused-import
        from channel_integrations.integrated_channel import signals
