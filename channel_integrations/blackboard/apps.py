"""
Enterprise Integrated Channel Blackboard Django application initialization.
"""

from django.apps import AppConfig

CHANNEL_NAME = 'channel_integrations.blackboard'
VERBOSE_NAME = 'Enterprise Blackboard Integration (Experimental)'
BRIEF_CHANNEL_NAME = 'blackboard'


class BlackboardConfig(AppConfig):
    """
    Configuration for the Enterprise Integrated Channel Blackboard Django application.
    """
    name = CHANNEL_NAME
    verbose_name = VERBOSE_NAME
    oauth_token_auth_path = "learn/api/public/v1/oauth2/token"
    brief_channel_name = BRIEF_CHANNEL_NAME
    label = 'blackboard_channel'
