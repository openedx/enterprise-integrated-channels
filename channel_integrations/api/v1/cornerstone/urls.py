"""
    url mappings for channel_integrations/api/v1/cornerstone/
"""

from django.urls import path
from rest_framework import routers

from .views import CornerstoneConfigurationViewSet, CornerstoneLearnerInformationView

app_name = 'cornerstone'
router = routers.DefaultRouter()
router.register(r'configuration', CornerstoneConfigurationViewSet, basename="configuration")
urlpatterns = [
    path('save-learner-information', CornerstoneLearnerInformationView.as_view(),
         name='save-learner-information'
         ),
]

urlpatterns += router.urls
