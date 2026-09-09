"""
Viewsets for channel_integrations/v1/canvas/
"""
from rest_framework import permissions, viewsets

from channel_integrations.api.v1.mixins import PermissionRequiredForIntegratedChannelMixin
from channel_integrations.canvas.models import CanvasEnterpriseCustomerConfiguration

from .serializers import CanvasEnterpriseCustomerConfigurationSerializer


class CanvasConfigurationViewSet(PermissionRequiredForIntegratedChannelMixin, viewsets.ModelViewSet):
    serializer_class = CanvasEnterpriseCustomerConfigurationSerializer
    permission_classes = (permissions.IsAuthenticated,)
    permission_required = 'enterprise.can_access_admin_dashboard'

    configuration_model = CanvasEnterpriseCustomerConfiguration
