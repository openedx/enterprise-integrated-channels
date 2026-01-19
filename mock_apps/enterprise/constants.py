"""
Enterprise Django application constants.
"""

TRANSMISSION_MARK_CREATE = 'create'
TRANSMISSION_MARK_UPDATE = 'update'
TRANSMISSION_MARK_DELETE = 'delete'

HTTP_STATUS_STRINGS = {
    400: 'The request was invalid, check the fields you entered are correct.',
    401: 'The request was unauthorized, check your credentials.',
    403: 'The request was rejected because it did not have the rights to access the content.',
    404: 'The requested resource was not found.',
    408: 'The request timed out.',
    429: 'The user has sent too many requests.',
    500: 'An internal problem on our side interfered.',
    503: 'The server is temporarily unavailable.',
}


ENTERPRISE_ADMIN_ROLE = 'enterprise_admin'

# context to give access to all resources
ALL_ACCESS_CONTEXT = '*'

# ContentFilter field types for validation.
CONTENT_FILTER_FIELD_TYPES = {
    'key': {'type': list, 'subtype': str},
    'first_enrollable_paid_seat_price__lte': {'type': str}
}

MAX_ALLOWED_TEXT_LENGTH = 16_000_000
EXEC_ED_COURSE_TYPE = "executive-education-2u"
IC_CREATE_ACTION = 'create'
IC_UPDATE_ACTION = 'update'
IC_DELETE_ACTION = 'delete'
EXEC_ED_CONTENT_DESCRIPTION_TAG = ("This instructor-led Executive Education course is "
                                   "presented by GetSmarter, an edX partner. ")


class FulfillmentTypes:
    LICENSE = 'license'
    LEARNER_CREDIT = 'learner_credit'
    COUPON_CODE = 'coupon_code'
    CHOICES = [(choice, choice.capitalize().replace('_', ' ')) for choice in (LICENSE, LEARNER_CREDIT, COUPON_CODE)]


class DefaultColors:
    """
    Class to group the default branding color codes.
    These color codes originated in the Enterprise Learner Portal.
    """
    PRIMARY = '#2D494E'
    SECONDARY = '#F2F0EF'
    TERTIARY = '#D23228'


# Course Modes
VERIFIED_COURSE_MODE = 'verified'
AUDIT_COURSE_MODE = 'audit'


class CourseModes:
    """
    Class to group modes that a course might have.
    """

    AUDIT = 'audit'
    CREDIT = 'credit'
    HONOR = 'honor'
    NO_ID_PROFESSIONAL = 'no-id-professional'
    PROFESSIONAL = 'professional'
    VERIFIED = 'verified'
    UNPAID_EXECUTIVE_EDUCATION = 'unpaid-executive-education'


# Course mode sorting based on slug
COURSE_MODE_SORT_ORDER = [
    CourseModes.VERIFIED,
    CourseModes.PROFESSIONAL,
    CourseModes.NO_ID_PROFESSIONAL,
    CourseModes.AUDIT,
    CourseModes.HONOR,
    CourseModes.UNPAID_EXECUTIVE_EDUCATION,
]

def json_serialized_course_modes():
    """
    :return: serialized course modes.
    """
    return COURSE_MODE_SORT_ORDER
