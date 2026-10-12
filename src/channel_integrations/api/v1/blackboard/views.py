"""
Viewsets for channel_integrations/v1/blackboard/
"""
from rest_framework import permissions, viewsets

from channel_integrations.api.v1.mixins import PermissionRequiredForIntegratedChannelMixin
from channel_integrations.blackboard.models import (
    BlackboardEnterpriseCustomerConfiguration,
    BlackboardGlobalConfiguration,
)

from .serializers import BlackboardConfigSerializer, BlackboardGlobalConfigSerializer


class BlackboardConfigurationViewSet(PermissionRequiredForIntegratedChannelMixin, viewsets.ModelViewSet):
    serializer_class = BlackboardConfigSerializer
    permission_classes = (permissions.IsAuthenticated,)
    permission_required = 'enterprise.can_access_admin_dashboard'

    configuration_model = BlackboardEnterpriseCustomerConfiguration


class BlackboardGlobalConfigurationViewSet(viewsets.ModelViewSet):
    queryset = BlackboardGlobalConfiguration.active_config.all()
    serializer_class = BlackboardGlobalConfigSerializer
    permission_classes = (permissions.IsAuthenticated,)
    permission_required = 'enterprise.can_access_admin_dashboard'

    configuration_model = BlackboardGlobalConfiguration
