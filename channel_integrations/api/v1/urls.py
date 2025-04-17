"""
URL definitions for v1 Integrated Channel API endpoints.
"""

from django.urls import include, path

from .views import IntegratedChannelHealthCheckView, IntegratedChannelsBaseViewSet

app_name = 'v1'
urlpatterns = [
    path('canvas/', include('channel_integrations.api.v1.canvas.urls')),
    path('moodle/', include('channel_integrations.api.v1.moodle.urls')),
    path('blackboard/', include('channel_integrations.api.v1.blackboard.urls')),
    path('sap_success_factors/', include('channel_integrations.api.v1.sap_success_factors.urls')),
    path('degreed2/', include('channel_integrations.api.v1.degreed2.urls')),
    path('cornerstone/', include('channel_integrations.api.v1.cornerstone.urls')),
    path('configs/health-check', IntegratedChannelHealthCheckView.as_view(), name='health_check'),
    path('configs/', IntegratedChannelsBaseViewSet.as_view({'get': 'list'}), name='configs'),
    path('logs/', include('channel_integrations.api.v1.logs.urls')),
]
