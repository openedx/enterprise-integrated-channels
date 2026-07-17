"""
URL definitions for Cornerstone API.
"""

from django.urls import path

from channel_integrations.cornerstone.views import CornerstoneCoursesListView

urlpatterns = [
    path('course-list', CornerstoneCoursesListView.as_view(),
         name='cornerstone-course-list'
         )
]
