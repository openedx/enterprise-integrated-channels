"""
Utilities to get details from the course catalog API.
"""
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from enterprise.utils import NotConnectedToOpenEdX, get_configuration_value_for_site
from enterprise.api_client.client import UserAPIClient

try:
    from openedx.core.djangoapps.catalog.models import CatalogIntegration
except ImportError:
    CatalogIntegration = None

try:
    from openedx.core.lib.edx_api_utils import get_api_data
except ImportError:
    get_api_data = None



class CourseCatalogApiClient(UserAPIClient):
    """
    The API client to make calls to the Catalog API.
    """
    APPEND_SLASH = True

    SEARCH_ALL_ENDPOINT = 'search/all/'
    CATALOGS_COURSES_ENDPOINT = 'catalogs/{}/courses/'
    COURSES_ENDPOINT = 'courses'
    COURSE_RUNS_ENDPOINT = 'course_runs'
    PROGRAMS_ENDPOINT = 'programs'
    PROGRAM_TYPES_ENDPOINT = 'program_types'

    DEFAULT_VALUE_SAFEGUARD = object()

    def __init__(self, user, site=None):
        """
        Check required services are up and running, instantiate the client.
        """
        if CatalogIntegration is None:
            raise NotConnectedToOpenEdX(
                _("To get a CatalogIntegration object, this package must be "
                  "installed in an Open edX environment.")
            )
        if get_api_data is None:
            raise NotConnectedToOpenEdX(
                _("To parse a Catalog API response, this package must be "
                  "installed in an Open edX environment.")
            )

        self.API_BASE_URL = get_configuration_value_for_site(  # pylint: disable=invalid-name
            site,
            'COURSE_CATALOG_API_URL',
            settings.COURSE_CATALOG_API_URL
        )
        super().__init__(user)


def get_course_catalog_api_service_client(site=None):
    return CourseCatalogApiServiceClient(site=site)


class CourseCatalogApiServiceClient(CourseCatalogApiClient):
    """
    Catalog API client which uses the configured Catalog service user.
    """

    def __init__(self, site=None):
        """
        Create an Course Catalog API client setup with authentication for the
        configured catalog service user.
        """
        if CatalogIntegration is None:
            raise NotConnectedToOpenEdX(
                _("To get a CatalogIntegration object, this package must be "
                  "installed in an Open edX environment.")
            )

        catalog_integration = CatalogIntegration.current()
        if catalog_integration.enabled:
            try:
                user = catalog_integration.get_service_user()
                super().__init__(user, site)
            except ObjectDoesNotExist as error:
                raise ImproperlyConfigured(
                    _("The configured CatalogIntegration service user does not exist.")
                ) from error
        else:
            raise ImproperlyConfigured(_("There is no active CatalogIntegration."))

    def program_exists(self, program_uuid):
        """
        Get whether the program exists or not.
        """
        return bool(self.get_program_by_uuid(program_uuid))
