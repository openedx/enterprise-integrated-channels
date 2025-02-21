"""
URL definitions for Blackboard API.
"""

from django.urls import path

from channel_integrations.blackboard.views import BlackboardCompleteOAuthView

urlpatterns = [
    path('oauth-complete', BlackboardCompleteOAuthView.as_view(),
         name='blackboard-oauth-complete'
         ),
]
