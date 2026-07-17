"""
Viewsets related to the channel_integrations Degreed2 model
"""
from rest_framework import permissions, viewsets

from channel_integrations.api.v1.mixins import PermissionRequiredForIntegratedChannelMixin
from channel_integrations.degreed2.models import Degreed2EnterpriseCustomerConfiguration

from .serializers import Degreed2ConfigSerializer


class Degreed2ConfigurationViewSet(PermissionRequiredForIntegratedChannelMixin, viewsets.ModelViewSet):
    serializer_class = Degreed2ConfigSerializer
    permission_classes = (permissions.IsAuthenticated,)
    permission_required = 'enterprise.can_access_admin_dashboard'

    configuration_model = Degreed2EnterpriseCustomerConfiguration
