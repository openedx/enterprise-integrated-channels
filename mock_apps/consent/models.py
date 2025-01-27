class DataSharingConsent:
    """
    An abstract representation of Data Sharing Consent granted to an Enterprise for a course by a User.

    The model is used to store a persistent, historical consent state for users granting, not granting, or revoking
    data sharing consent to an Enterprise for a course.

    .. pii: The username field inherited from Consent contains PII.
    .. pii_types: username
    .. pii_retirement: consumer_api
    """
