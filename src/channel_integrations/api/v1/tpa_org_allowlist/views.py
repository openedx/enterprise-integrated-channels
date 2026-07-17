"""
Viewset for TPA Org Allowlist.
"""
from uuid import UUID

import crum
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from edx_rbac.utils import has_access_to_all

from channel_integrations.api.v1.mixins import PermissionRequiredForIntegratedChannelMixin
from channel_integrations.integrated_channel.models import TpaOrgAllowlist
from .serializers import TpaOrgAllowlistSerializer


class TpaOrgAllowlistViewSet(
    PermissionRequiredForIntegratedChannelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Viewset for managing TPA org allowlist entries.
    Supports create, list, retrieve, destroy, and validate.
    """
    serializer_class = TpaOrgAllowlistSerializer
    permission_classes = (permissions.IsAuthenticated,)
    permission_required = 'enterprise.can_access_admin_dashboard'
    allowed_roles = ['tpa_org_allowlist_admin']
    configuration_model = TpaOrgAllowlist
    pagination_class = None

    def check_permissions(self, request):
        """
        Use accessible_contexts for all actions (not just list) so that
        DB-based role assignments are honoured without requiring the django-rules
        permission backend or JWT predicates.

        Superusers bypass the check. All other users must have at least one
        accessible enterprise context via their role assignments.
        """
        crum.set_current_request(request)
        if request.user.is_superuser:
            return
        if not self.accessible_contexts:
            self.permission_denied(request)

    def get_queryset(self):
        """
        For list actions, delegate to the parent mixin which handles enterprise
        scoping via accessible_contexts and the enterprise_customer query param.

        For retrieve and destroy, the parent mixin returns base_queryset without
        enterprise scoping — override to always restrict to the caller's accessible
        enterprise contexts so entries from other enterprises return 404.
        """
        if self.action == 'list':
            return super().get_queryset()
        qs = TpaOrgAllowlist.objects.all()
        if not has_access_to_all(self.accessible_contexts):
            qs = qs.filter(enterprise_customer_id__in=self.accessible_contexts)
        return qs

    @action(detail=False, methods=['get'], url_path='validate')
    def validate(self, request):
        """
        Returns 200 if the given tpa_org_id is in the allowlist, 404 otherwise.
        Intended for use by Auth0 Actions at login time.

        The enterprise customer scope is derived from the caller's credentials.
        Tokens scoped to a specific enterprise (the normal service-user case) do not
        need to pass enterprise_customer. Tokens with global access (ALL_ACCESS_CONTEXT)
        must supply enterprise_customer explicitly.
        """
        tpa_org_id = request.query_params.get('tpa_org_id')
        if not tpa_org_id:
            return Response(
                {'detail': 'tpa_org_id is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        enterprise_uuids = self.accessible_contexts

        if has_access_to_all(enterprise_uuids):
            enterprise_customer_param = request.query_params.get('enterprise_customer')
            if not enterprise_customer_param:
                return Response(
                    {'detail': 'enterprise_customer is required for tokens with global access.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                enterprise_uuids = {str(UUID(enterprise_customer_param))}
            except (ValueError, AttributeError):
                return Response(
                    {'detail': f'{enterprise_customer_param} is not a valid UUID.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        exists = TpaOrgAllowlist.objects.filter(
            enterprise_customer_id__in=enterprise_uuids,
            tpa_org_id=tpa_org_id,
        ).exists()

        if exists:
            return Response({'detail': 'Authorised.'}, status=status.HTTP_200_OK)
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
