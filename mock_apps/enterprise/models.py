"""
Database models for enterprise.
"""
from django.db import models


class EnterpriseCustomerCatalog:
    """
    Store catalog information from course discovery specifically for Enterprises.

    We use this model to consolidate course catalog information, which includes
    information about catalogs, courses, programs, and possibly more in the
    future, as the course discovery service evolves.

    .. no_pii:
    """


class EnterpriseCourseEnrollment:
    """
    Store information about the enrollment of a user in a course.

    This model is the central source of truth for information about
    whether a particular user, linked to a particular EnterpriseCustomer,
    has been enrolled in a course, and is the repository for any other
    relevant metadata about such an enrollment.

    Do not delete records of this model - there are downstream business
    reporting processes that rely them, even if the underlying ``student.CourseEnrollment``
    record has been marked inactive/un-enrolled.  As a consequence, the only
    way to determine if a given ``EnterpriseCourseEnrollment`` is currently active
    is to examine the ``is_active`` field of the associated ``student.CourseEnrollment``.

    .. no_pii:
    """


class EnterpriseCustomer:
    """
    Enterprise Customer is an organization or a group of people that "consumes" courses.

    Users associated with an Enterprise Customer take courses on the edX platform.

    Enterprise Customer might be providing certain benefits to their members, like discounts to paid course
    enrollments, and also might request (or require) sharing learner results with them.

    Fields:
        uuid (UUIDField, PRIMARY KEY): Enterprise Customer code - used to reference this Enterprise Customer in
            other parts of the system (SSO, ecommerce, analytics etc.).
        name (:class:`django.db.models.CharField`): Enterprise Customer name.
        active (:class:`django.db.models.BooleanField`): used to mark inactive Enterprise Customers - implements
            "soft delete" pattern.

    .. no_pii:
    """

    enterprise_customer_catalogs = models.ManyToManyField(
    EnterpriseCustomerCatalog,
    verbose_name="Enterprise Customer Catalogs",
    )