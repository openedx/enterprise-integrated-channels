"""
Enterprise Django application constants.
"""

TRANSMISSION_MARK_CREATE = 'create'
TRANSMISSION_MARK_UPDATE = 'update'
TRANSMISSION_MARK_DELETE = 'delete'

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
