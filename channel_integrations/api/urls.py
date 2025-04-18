"""
URL definitions for channel_integrations API endpoint.
"""

from django.urls import include, path

app_name = 'api'
urlpatterns = [
    path('v1/', include('channel_integrations.api.v1.urls'), name='api')
]
