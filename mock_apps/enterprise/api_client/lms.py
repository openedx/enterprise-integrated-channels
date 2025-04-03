"""
Utilities to get details from the course catalog API.
"""
import logging
from urllib.parse import urljoin

from requests.exceptions import HTTPError, RequestException, Timeout  # pylint: disable=redefined-builtin

from django.conf import settings

from enterprise.api_client.client import BackendServiceAPIClient, UserAPIClient


LOGGER = logging.getLogger(__name__)


class EnrollmentApiClient(BackendServiceAPIClient):
    """
    The API client to make calls to the Enrollment API.
    """

    API_BASE_URL = settings.ENTERPRISE_ENROLLMENT_API_URL

    def get_course_details(self, course_id):
        """
        Query the Enrollment API for the course details of the given course_id.

        Args:
            course_id (str): The string value of the course's unique identifier

        Returns:
            dict: A dictionary containing details about the course, in an enrollment context (allowed modes, etc.)
        """
        api_url = self.get_api_url(f"course/{course_id}")
        try:
            response = self.client.get(api_url)
            response.raise_for_status()
            return response.json()
        except (RequestException, ConnectionError, Timeout):
            LOGGER.exception(
                'Failed to retrieve course enrollment details for course [%s].', course_id
            )
            return {}


class GradesApiClient(UserAPIClient):
    """
    The API client to make calls to the LMS Grades API.

    Note that this API client requires a JWT token, and so it keeps its token alive.
    """

    def get_course_assessment_grades(self, course_id, username):
        return []


class ThirdPartyAuthApiClient(UserAPIClient):
    """
    The API client to make calls to the Third Party Auth API.
    """

    API_BASE_URL = urljoin(f"{settings.LMS_INTERNAL_ROOT_URL}/", "api/third_party_auth/v0/")

    @UserAPIClient.refresh_token
    def get_remote_id(self, identity_provider, username):
        """
        Retrieve the remote identifier for the given username.

        Args:
        * ``identity_provider`` (str): identifier slug for the third-party authentication service used during SSO.
        * ``username`` (str): The username ID identifying the user for which to retrieve the remote name.

        Returns:
            string or None: the remote name of the given user.  None if not found.
        """
        return self._get_results(identity_provider, 'username', username, 'remote_id')

    @UserAPIClient.refresh_token
    def get_username_from_remote_id(self, identity_provider, remote_id):
        """
        Retrieve the remote identifier for the given username.

        Args:
        * ``identity_provider`` (str): identifier slug for the third-party authentication service used during SSO.
        * ``remote_id`` (str): The remote id identifying the user for which to retrieve the usernamename.

        Returns:
            string or None: the username of the given user.  None if not found.
        """
        return self._get_results(identity_provider, 'remote_id', remote_id, 'username')

    def _get_results(self, identity_provider, param_name, param_value, result_field_name):
        """
        Calls the third party auth api endpoint to get the mapping between usernames and remote ids.
        """
        api_url = self.get_api_url(f"providers/{identity_provider}/users")
        try:
            kwargs = {param_name: param_value}
            response = self.client.get(api_url, params=kwargs)
            response.raise_for_status()
            results = response.json().get('results', [])
        except HTTPError as err:
            if err.response.status_code == 404:
                LOGGER.error(
                    'Username not found for third party provider={%s}, {%s}={%s}',
                    identity_provider,
                    param_name,
                    param_value
                )
                results = []
            else:
                raise

        for row in results:
            if row.get(param_name) == param_value:
                return row.get(result_field_name)
        return None
