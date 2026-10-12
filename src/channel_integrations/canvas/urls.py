"""
URL definitions for Canvas API.
"""

from django.urls import path

from channel_integrations.canvas.views import CanvasCompleteOAuthView

urlpatterns = [
    path('oauth-complete', CanvasCompleteOAuthView.as_view(),
         name='canvas-oauth-complete'
         ),
]
