import datetime
from logging import getLogger
import pytz
from uuid import UUID

from urllib.parse import parse_qs, urlparse, urlsplit, urlunsplit, urlencode
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime
from django.db.models.query import QuerySet
from django.http import Http404

from enterprise.constants import MAX_ALLOWED_TEXT_LENGTH


User = get_user_model()
LOGGER = getLogger(__name__)

try:
    from common.djangoapps.third_party_auth.provider import Registry
except ImportError as exception:
    LOGGER.debug("Could not import Registry from common.djangoapps.third_party_auth.provider")
    LOGGER.debug(exception)
    Registry = None

try:
    from social_django.models import UserSocialAuth # type: ignore
except ImportError:
    UserSocialAuth = None

try:
    from common.djangoapps.track import segment
except ImportError as exception:
    LOGGER.debug("Could not import segment from common.djangoapps.track")
    LOGGER.debug(exception)
    segment = None

LMS_API_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
LMS_API_DATETIME_FORMAT_WITHOUT_TIMEZONE = '%Y-%m-%dT%H:%M:%S'


def get_content_metadata_item_id(content_metadata_item):
    if content_metadata_item['content_type'] == 'program':
        return content_metadata_item['uuid']
    return content_metadata_item['key']


def localized_utcnow():
    return pytz.UTC.localize(datetime.datetime.utcnow())  # pylint: disable=no-value-for-parameter


def truncate_string(string, max_length=MAX_ALLOWED_TEXT_LENGTH):
    was_truncated = False
    if len(string) > max_length:
        truncated_string = string[:max_length]
        was_truncated = True
        return (truncated_string, was_truncated)
    return (string, was_truncated)


def enterprise_course_enrollment_model():
    return apps.get_model('enterprise', 'EnterpriseCourseEnrollment')


def get_enterprise_uuids_for_user_and_course(auth_user, course_run_id, is_customer_active=None):
    return enterprise_course_enrollment_model().get_enterprise_uuids_with_user_and_course(
        auth_user.id,
        course_run_id,
        is_customer_active=is_customer_active,
    )


def parse_datetime_handle_invalid(datetime_value):
    if not datetime_value:
        return None
    try:
        if not isinstance(datetime_value, datetime.datetime):
            datetime_value = parse_datetime(datetime_value)
        if not datetime_value:
            return None
        return datetime_value.replace(tzinfo=pytz.UTC)
    except TypeError:
        return None

def get_configuration_value_for_site(site, key, default=None):
    """
    Get the site configuration value for a key, unless a site configuration does not exist for that site.

    Useful for testing when no Site Configuration exists in edx-enterprise or if a site in LMS doesn't have
    a configuration tied to it.

    :param site: A Site model object
    :param key: The name of the value to retrieve
    :param default: The default response if there's no key in site config or settings
    :return: The value located at that key in the site configuration or settings file.
    """
    if hasattr(site, 'configuration'):
        return site.configuration.get_value(key, default)
    return default


def parse_lms_api_datetime(datetime_string, datetime_format=LMS_API_DATETIME_FORMAT):
    if isinstance(datetime_string, datetime.datetime):
        date_time = datetime_string
    else:
        try:
            date_time = datetime.datetime.strptime(datetime_string, datetime_format)
        except ValueError:
            date_time = datetime.datetime.strptime(datetime_string, LMS_API_DATETIME_FORMAT_WITHOUT_TIMEZONE)

    # If the datetime format didn't include a timezone, then set to UTC.
    # Note that if we're using the default LMS_API_DATETIME_FORMAT, it ends in 'Z',
    # which denotes UTC for ISO-8661.
    if date_time.tzinfo is None:
        date_time = date_time.replace(tzinfo=datetime.timezone.utc)
    return date_time


def update_query_parameters(url, query_parameters):
    """
    Return url with updated query parameters.

    Arguments:
        url (str): Original url whose query parameters need to be updated.
        query_parameters (dict): A dictionary containing query parameters to be added to course selection url.

    Returns:
        (slug): slug identifier for the identity provider that can be used for identity verification of
            users associated the enterprise customer of the given user.

    """
    scheme, netloc, path, query_string, fragment = urlsplit(url)
    url_params = parse_qs(query_string)

    # Update url query parameters
    url_params.update(query_parameters)

    return urlunsplit(
        (scheme, netloc, path, urlencode(sorted(url_params.items()), doseq=True), fragment),
    )


def get_identity_provider(provider_id):
    """
    Get Identity Provider with given id.

    Return:
        Instance of ProviderConfig or None.
    """
    try:
        return Registry and Registry.get(provider_id)
    except ValueError:
        return None


def get_social_auth_from_idp(idp, user=None, user_idp_id=None):
    """
    Return social auth entry of user for given enterprise IDP.

    idp (EnterpriseCustomerIdentityProvider): EnterpriseCustomerIdentityProvider Object
    user (User): User Object
    user_idp_id (str): User id of user in third party LMS
    """

    if idp:
        tpa_provider = get_identity_provider(idp.provider_id)
        filter_kwargs = {
            'provider': tpa_provider.backend_name,
            'uid__contains': tpa_provider.provider_id[5:]
        }
        if user_idp_id:
            provider_slug = tpa_provider.provider_id[5:]
            social_auth_uid = '{}:{}'.format(provider_slug, user_idp_id)
            filter_kwargs['uid'] = social_auth_uid
        else:
            filter_kwargs['user'] = user

        user_social_auth = UserSocialAuth.objects.select_related('user').filter(**filter_kwargs).first()

        return user_social_auth if user_social_auth else None

    return None


def batch(iterable, batch_size=1):
    """
    Break up an iterable into equal-sized batches.

    Arguments:
        iterable (e.g. list): an iterable to batch
        batch_size (int): the size of each batch. Defaults to 1.
    Returns:
        generator: iterates through each batch of an iterable
    """
    if isinstance(iterable, QuerySet):
        iterable_len = iterable.count()
    else:
        iterable_len = len(iterable)
    for index in range(0, iterable_len, batch_size):
        yield iterable[index:min(index + batch_size, iterable_len)]


def get_user_valid_idp(user, enterprise_customer):
    """
    Return the default idp if it has user social auth record else it
    will return any idp with valid user social auth record

    user (User): user object
    enterprise_customer (EnterpriseCustomer): EnterpriseCustomer object
    """
    valid_identity_provider = None

    # If default idp provider has UserSocialAuth record then it has the highest priority.
    if get_social_auth_from_idp(enterprise_customer.default_provider_idp, user=user):
        valid_identity_provider = enterprise_customer.default_provider_idp
    else:
        for idp in enterprise_customer.identity_providers:
            if get_social_auth_from_idp(idp, user=user):
                valid_identity_provider = idp
                break
    return valid_identity_provider


class NotConnectedToOpenEdX(Exception):
    """
    Exception to raise when not connected to OpenEdX.
    """

    def __init__(self, *args, **kwargs):
        """
        Log a warning and initialize the exception.
        """
        LOGGER.warning('edx-enterprise unexpectedly failed as if not installed in an OpenEdX platform')
        super().__init__(*args, **kwargs)


class CourseEnrollmentDowngradeError(Exception):
    """
    Exception to raise when an enrollment attempts to enroll the user in an unpaid mode when they are in a paid mode.
    """


class CourseEnrollmentPermissionError(Exception):
    """
    Exception to raise when an enterprise attempts to use enrollment features it's not configured to use.
    """


SELF_ENROLL_EMAIL_TEMPLATE_TYPE = 'self_enroll'


def track_event(user_id, event_name, properties):
    """
    Emit a track event to segment (and forwarded to GA) for some parts of the Enterprise workflows.
    """
    # Only call the endpoint if the import was successful.
    if segment:
        segment.track(user_id, event_name, properties)

def get_advertised_course_run(course_runs):
    return {}

def get_closest_course_run(course_runs):
    return {}

def get_course_run_duration_info(course_run):
    return []

def is_course_run_active(course_run):
    return True

def get_enterprise_customer(uuid):
    return {}


def _get_service_worker(service_worker_username):
    """
    Retrieve the specified service worker object. If user cannot be found then returns None.
    """
    try:
        return User.objects.get(username=service_worker_username)
    except User.DoesNotExist:
        return None


def get_enterprise_worker_user():
    """
    Return the user object of enterprise worker user.
    """
    return _get_service_worker(settings.ENTERPRISE_SERVICE_WORKER_USERNAME)


def traverse_pagination(response, client, api_url):
    """
    Traverse a paginated API response.

    Extracts and concatenates "results" (list of dict) returned by DRF-powered
    APIs.

    Arguments:
        response (Dict): Current response dict from service API;
        client (requests.Session): either the OAuthAPIClient (from edx_rest_api_client) or requests.Session object;
        api_url (str): API endpoint URL to call.

    Returns:
        list of dict.

    """
    results = response.get('results', [])

    next_page = response.get('next')
    while next_page:
        querystring = parse_qs(urlparse(next_page).query, keep_blank_values=True)
        response = client.get(api_url, params=querystring)
        response.raise_for_status()
        response = response.json()
        results += response.get('results', [])
        next_page = response.get('next')

    return results

def get_oauth2authentication_class():
    return {}

def get_language_code(language):
    return {}

def get_advertised_or_closest_course_run(course_runs):
    return {}

def get_duration_of_course_or_courserun(course_run):
    return "", "", ""


def is_course_run_published(course_run):
    """
    Return True if the course run's status value is "published".
    """
    if course_run:
        if course_run.get('status') == 'published':
            return True
    return False


def is_course_run_enrollable(course_run):
    """
    Return true if the course run is enrollable, false otherwise.

    We look for the following criteria:

    1. end date is greater than a reasonably-defined enrollment window, or undefined.
        A reasonably-defined enrollment window is 1 day before course run end date.

    2. enrollment_start is less than now, or undefined.

    3. enrollment_end is greater than now, or undefined.
    """
    # Check if the course run is unpublished (sometimes these sneak through)
    if not is_course_run_published(course_run):
        return False

    now = datetime.datetime.now(pytz.UTC)
    reasonable_enrollment_window = now + datetime.timedelta(days=1)
    end = parse_datetime_handle_invalid(course_run.get('end'))
    enrollment_start = parse_datetime_handle_invalid(course_run.get('enrollment_start'))
    enrollment_end = parse_datetime_handle_invalid(course_run.get('enrollment_end'))
    return (not end or end > reasonable_enrollment_window) and \
           (not enrollment_start or enrollment_start < now) and \
           (not enrollment_end or enrollment_end > now)


def is_course_run_available_for_enrollment(course_run):
    """
    Check if a course run is available for enrollment.
    """
    # If the course run is Archived, it's not available for enrollment
    if course_run.get('availability') not in ['Current', 'Starting Soon', 'Upcoming']:
        return False

    # If the course run is not "enrollable", it's not available for enrollment
    if not is_course_run_enrollable(course_run):
        return False

    return True


def has_course_run_available_for_enrollment(course_runs):
    """
        Iterates over all course runs to check if there any course run that is available for enrollment.

    Argument:
        course_runs: list of course runs

    Returns:
        True if found else false
    """
    for course_run in course_runs:
        if is_course_run_available_for_enrollment(course_run):
            return True
    return False


def get_last_course_run_end_date(course_runs):
    """
    Returns the end date of the course run that falls at the end.
    """
    latest_end_date = None
    if course_runs:
        try:
            latest_end_date = max(course_run.get('end') for course_run in course_runs if
                                  parse_datetime_handle_invalid(course_run.get('end')) is not None)
        except ValueError:
            latest_end_date = None
    return latest_end_date


def enterprise_customer_model():
    """
    Returns the ``EnterpriseCustomer`` class.
    """
    return apps.get_model('enterprise', 'EnterpriseCustomer')


def get_enterprise_customer_or_404(enterprise_uuid):
    """
    Given an EnterpriseCustomer UUID, return the corresponding EnterpriseCustomer or raise a 404.

    Arguments:
        enterprise_uuid (str): The UUID (in string form) of the EnterpriseCustomer to fetch.

    Returns:
        (EnterpriseCustomer): The EnterpriseCustomer given the UUID.

    """
    EnterpriseCustomer = enterprise_customer_model()
    try:
        enterprise_uuid = UUID(enterprise_uuid)
        return EnterpriseCustomer.objects.get(uuid=enterprise_uuid)
    except (TypeError, ValueError, EnterpriseCustomer.DoesNotExist) as no_customer_error:
        LOGGER.error('Unable to find enterprise customer for UUID: [%s]', enterprise_uuid)
        raise Http404 from no_customer_error


def get_enterprise_customer_user(user_id, enterprise_uuid):
    """
    Return the object for EnterpriseCustomerUser.

    Arguments:
        user_id (str): user identifier
        enterprise_uuid (UUID): Universally unique identifier for the enterprise customer.

    Returns:
        (EnterpriseCustomerUser): enterprise customer user record

    """
    EnterpriseCustomerUser = apps.get_model('enterprise', 'EnterpriseCustomerUser')
    try:
        return EnterpriseCustomerUser.objects.get(
            enterprise_customer__uuid=enterprise_uuid,
            user_id=user_id
        )
    except EnterpriseCustomerUser.DoesNotExist:
        return None
