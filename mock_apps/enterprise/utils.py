import datetime
import pytz

from django.apps import apps
from django.utils.dateparse import parse_datetime

from enterprise.logging import getEnterpriseLogger
from enterprise.constants import MAX_ALLOWED_TEXT_LENGTH


LMS_API_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
LMS_API_DATETIME_FORMAT_WITHOUT_TIMEZONE = '%Y-%m-%dT%H:%M:%S'

LOGGER = getEnterpriseLogger(__name__)


def get_content_metadata_item_id(content_metadata_item):
    """
    Return the unique identifier given a content metadata item dictionary.
    """
    if content_metadata_item['content_type'] == 'program':
        return content_metadata_item['uuid']
    return content_metadata_item['key']


def localized_utcnow():
    """Helper function to return localized utcnow()."""
    return pytz.UTC.localize(datetime.datetime.utcnow())  # pylint: disable=no-value-for-parameter


def truncate_string(string, max_length=MAX_ALLOWED_TEXT_LENGTH):
    """
    Truncate a string to the specified max length.
    If max length is not specified, it will be set to MAX_ALLOWED_TEXT_LENGTH.

    Returns:
        (tuple): (truncated_string, was_truncated)
    """
    was_truncated = False
    if len(string) > max_length:
        truncated_string = string[:max_length]
        was_truncated = True
        return (truncated_string, was_truncated)
    return (string, was_truncated)


def enterprise_course_enrollment_model():
    """
    Returns the ``EnterpriseCourseEnrollment`` class.
    """
    return apps.get_model('enterprise', 'EnterpriseCourseEnrollment')


def get_enterprise_uuids_for_user_and_course(auth_user, course_run_id, is_customer_active=None):
    """
    Get the ``EnterpriseCustomer`` UUID(s) associated with a user and a course id``.

    Some users are associated with an enterprise customer via `EnterpriseCustomerUser` model,
        1. if given user is enrolled in a specific course via an enterprise customer enrollment,
           return related enterprise customers as a list.
        2. otherwise return empty list.

    Arguments:
        auth_user (contrib.auth.User): Django User
        course_run_id (str): Course Run to lookup an enrollment against.
        active: (boolean or None): Filter flag for returning active, inactive, or all uuids

    Returns:
        (list of str): enterprise customer uuids associated with the current user and course run or None

    """
    return enterprise_course_enrollment_model().get_enterprise_uuids_with_user_and_course(
        auth_user.id,
        course_run_id,
        is_customer_active=is_customer_active,
    )


def parse_datetime_handle_invalid(datetime_value):
    """
    Return the parsed version of a datetime string. If the string is invalid, return None.
    """
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



def parse_lms_api_datetime(datetime_string, datetime_format=LMS_API_DATETIME_FORMAT):
    """
    Parse a received datetime into a timezone-aware, Python datetime object.

    Arguments:
        datetime_string: A string to be parsed.
        datetime_format: A datetime format string to be used for parsing

    """
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




class NotConnectedToOpenEdX(Exception):
    """
    Exception to raise when not connected to OpenEdX.

    In general, this exception shouldn't be raised, because this package is
    designed to be installed directly inside an existing OpenEdX platform.
    """

    def __init__(self, *args, **kwargs):
        """
        Log a warning and initialize the exception.
        """
        LOGGER.warning('edx-enterprise unexpectedly failed as if not installed in an OpenEdX platform')
        super().__init__(*args, **kwargs)
