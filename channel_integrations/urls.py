"""
URLs for channel_integrations.
"""
from django.urls import path
from django.urls import include


urlpatterns = [
    path(
        'cornerstone/',
        include('channel_integrations.cornerstone.urls'),
        name='cornerstone'
    ),
    path(
        'canvas/',
        include('channel_integrations.canvas.urls'),
        name='canvas',
    ),
    path(
        'blackboard/',
        include('channel_integrations.blackboard.urls'),
        name='blackboard',
    ),
    path(
        'integrated_channels/api/',
        include('channel_integrations.api.urls')
    ),
]
