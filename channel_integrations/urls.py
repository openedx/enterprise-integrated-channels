"""
URLs for channel_integrations.
"""
from django.urls import re_path, include


urlpatterns = [
    re_path(
        r'^cornerstone/',
        include('channel_integrations.cornerstone.urls'),
        name='cornerstone'
    ),
    re_path(
        r'^canvas/',
        include('channel_integrations.canvas.urls'),
        name='canvas',
    ),
    re_path(
        r'^blackboard/',
        include('channel_integrations.blackboard.urls'),
        name='blackboard',
    ),
    re_path(
        r'^integrated_channels/api/',
        include('channel_integrations.api.urls')
    ),
]
