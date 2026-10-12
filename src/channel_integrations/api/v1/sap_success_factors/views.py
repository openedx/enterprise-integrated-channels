"""
Viewsets for channel_integrations/v1/sap_success_factors/
"""
from rest_framework import permissions, viewsets

from channel_integrations.api.v1.mixins import PermissionRequiredForIntegratedChannelMixin
from channel_integrations.sap_success_factors.models import SAPSuccessFactorsEnterpriseCustomerConfiguration

from .serializers import SAPSuccessFactorsConfigSerializer


class SAPSuccessFactorsConfigurationViewSet(PermissionRequiredForIntegratedChannelMixin, viewsets.ModelViewSet):
    serializer_class = SAPSuccessFactorsConfigSerializer
    permission_classes = (permissions.IsAuthenticated,)
    permission_required = 'enterprise.can_access_admin_dashboard'

    configuration_model = SAPSuccessFactorsEnterpriseCustomerConfiguration
