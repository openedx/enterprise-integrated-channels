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
EXEC_ED_CONTENT_DESCRIPTION_TAG = ("This instructor-led Executive Education course is "
                                   "presented by GetSmarter, an edX partner. ")
