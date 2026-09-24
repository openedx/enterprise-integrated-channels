"""
Viewsets for channel_integrations/v1/cornerstone/
"""
from logging import getLogger

from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication
from rest_framework import permissions, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND
from rest_framework.views import APIView

from django.contrib import auth
from django.db import transaction

from enterprise.api.throttles import ServiceUserThrottle
from enterprise.utils import get_enterprise_customer_or_404, get_enterprise_customer_user, localized_utcnow
from channel_integrations.api.v1.mixins import PermissionRequiredForIntegratedChannelMixin
from channel_integrations.cornerstone.models import CornerstoneEnterpriseCustomerConfiguration
from channel_integrations.cornerstone.utils import create_cornerstone_learner_data

from .serializers import CornerstoneConfigSerializer

LOGGER = getLogger(__name__)
User = auth.get_user_model()


class CornerstoneConfigurationViewSet(PermissionRequiredForIntegratedChannelMixin, viewsets.ModelViewSet):
    """Viewset for CornerstoneEnterpriseCustomerConfiguration"""
    serializer_class = CornerstoneConfigSerializer
    permission_classes = (permissions.IsAuthenticated,)
    permission_required = 'enterprise.can_access_admin_dashboard'

    configuration_model = CornerstoneEnterpriseCustomerConfiguration


class CornerstoneLearnerInformationView(APIView):
    """Viewset for saving information of a cornerstone learner"""
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JwtAuthentication, SessionAuthentication,)
    throttle_classes = (ServiceUserThrottle,)

    def post(self, request):
        """
            An endpoint to save a cornerstone learner information received from frontend.
            channel_integrations/api/v1/cornerstone/save-learner-information
            Requires a JSON object in the following format:
                {
                    "courseKey": "edX+DemoX",
                    "enterpriseUUID": "enterprise-uuid-goes-right-here",
                    "userGuid": "user-guid-from-csod",
                    "callbackUrl": "https://example.com/csod/callback/1",
                    "sessionToken": "123123123",
                    "subdomain": "edx.csod.com"
                }
        """
        user_id = request.user.id
        enterprise_customer_uuid = request.data.get('enterpriseUUID')
        enterprise_customer = get_enterprise_customer_or_404(enterprise_customer_uuid)
        course_key = request.data.get('courseKey')

        csod_user_guid = request.data.get('userGuid')
        csod_callback_url = request.data.get('callbackUrl')
        csod_session_token = request.data.get('sessionToken')
        csod_subdomain = request.data.get('subdomain')

        log_prefix = (
            f'integrated_channel=CSOD, '
            f'integrated_channel_enterprise_customer_uuid={enterprise_customer_uuid}, '
            f'integrated_channel_lms_user={user_id}, '
            f'integrated_channel_course_key={course_key}'
        )

        if not csod_session_token or not csod_subdomain:
            LOGGER.warning(
                f'{log_prefix}, missing required fields: '
                f'sessionToken={"<present>" if csod_session_token else "<missing>"}, subdomain={csod_subdomain}'
            )
            return Response(
                data={'error': 'sessionToken and subdomain are required'},
                status=HTTP_400_BAD_REQUEST
            )

        cornerstone_customer_configuration = (
            CornerstoneEnterpriseCustomerConfiguration.get_by_customer_and_subdomain(
                enterprise_customer=enterprise_customer,
                customer_subdomain=csod_subdomain
            )
        )
        if not cornerstone_customer_configuration:
            LOGGER.error(f'{log_prefix}, unable to find cornerstone config matching subdomain {csod_subdomain}')
            message = (
                f'Cornerstone information could not be saved for learner with user_id={user_id} '
                f'because no config exists with the subdomain {csod_subdomain}'
            )
            return Response(data={'error': message}, status=HTTP_404_NOT_FOUND)

        enterprise_customer_user = get_enterprise_customer_user(user_id, enterprise_customer_uuid)
        if not enterprise_customer_user:
            LOGGER.error(f'{log_prefix}, user is not linked to the given enterprise')
            message = (
                f'Cornerstone information could not be saved for learner with user_id={user_id} '
                f'because user is not linked to the given enterprise {enterprise_customer_uuid}'
            )
            return Response(data={'error': message}, status=HTTP_404_NOT_FOUND)

        with transaction.atomic():
            cornerstone_customer_configuration.session_token = csod_session_token
            cornerstone_customer_configuration.session_token_modified = localized_utcnow()
            cornerstone_customer_configuration.save()

            create_cornerstone_learner_data(
                user_id,
                csod_user_guid,
                csod_session_token,
                csod_callback_url,
                csod_subdomain,
                cornerstone_customer_configuration,
                course_key
            )

        return Response(status=HTTP_200_OK)
