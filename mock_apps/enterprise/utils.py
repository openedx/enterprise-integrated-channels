import datetime

import pytz
from django.apps import apps
from django.utils.dateparse import parse_datetime
from enterprise.constants import MAX_ALLOWED_TEXT_LENGTH

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




class NotConnectedToOpenEdX(Exception):
    """
    Exception to raise when not connected to OpenEdX.
    """


SELF_ENROLL_EMAIL_TEMPLATE_TYPE = 'self_enroll'

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

def get_enterprise_worker_user():
    return {}

def get_oauth2authentication_class():
    return {}

def get_language_code(language):
    return {}

def get_advertised_or_closest_course_run(course_runs):
    return {}

def get_duration_of_course_or_courserun(course_run):
    return "", "", ""

def is_course_run_available_for_enrollment(course_run):
    return True
