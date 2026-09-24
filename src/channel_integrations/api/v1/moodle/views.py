"""
Viewsets for channel_integrations/v1/moodle/
"""
from rest_framework import permissions, viewsets

from channel_integrations.api.v1.mixins import PermissionRequiredForIntegratedChannelMixin
from channel_integrations.moodle.models import MoodleEnterpriseCustomerConfiguration

from .serializers import MoodleConfigSerializer


class MoodleConfigurationViewSet(PermissionRequiredForIntegratedChannelMixin, viewsets.ModelViewSet):
    serializer_class = MoodleConfigSerializer
    permission_classes = (permissions.IsAuthenticated,)
    permission_required = 'enterprise.can_access_admin_dashboard'

    configuration_model = MoodleEnterpriseCustomerConfiguration
