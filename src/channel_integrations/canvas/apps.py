"""
Enterprise Integrated Channel Canvas Django application initialization.
"""

from django.apps import AppConfig


class CanvasConfig(AppConfig):
    """
    Configuration for the Enterprise Integrated Channel Canvas Django application.
    """

    name = "channel_integrations.canvas"
    verbose_name = "Enterprise Canvas Integration (Experimental)"
    label = "canvas_channel"
    oauth_token_auth_path = "login/oauth2/token"
