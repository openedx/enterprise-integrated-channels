"""
Database models for enterprise.
"""

import collections
from uuid import uuid4

from jsonfield.encoder import JSONEncoder
from jsonfield.fields import JSONField

from simple_history.models import HistoricalRecords

from django.core.exceptions import ObjectDoesNotExist
from django.contrib import auth
from django.db import models
from django.utils.functional import lazy
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel


from enterprise.constants import json_serialized_course_modes
from enterprise.logging import getEnterpriseLogger
from enterprise.validators import validate_content_filter_fields


LOGGER = getEnterpriseLogger(__name__)
User = auth.get_user_model()
mark_safe_lazy = lazy(mark_safe, str)


class EnterpriseCustomer(TimeStampedModel):
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

    class Meta:
        app_label = 'enterprise'
        verbose_name = _("Enterprise Customer")
        verbose_name_plural = _("Enterprise Customers")

    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=255, blank=False, null=False, help_text=_("Enterprise Customer name."))
    slug = models.SlugField(
        max_length=30, unique=True, default='default',
        help_text=(
            'A short string uniquely identifying this enterprise. '
            'Cannot contain spaces and should be a usable as a CSS class. Examples: "ubc", "mit-staging"'
        )
    )
    active = models.BooleanField(default=True)



class EnterpriseCatalogQuery(TimeStampedModel):
    """
    Stores a re-usable catalog query.

    This stored catalog query used in `EnterpriseCustomerCatalog` objects to build catalog's content_filter field.
    This is a saved instance of `content_filter` that can be re-used across different catalogs.

    .. no_pii:
    """

    title = models.CharField(
        max_length=255,
        blank=True,
        unique=True,
        null=True,
    )
    content_filter = JSONField(
        default={},
        blank=True,
        null=True,
        load_kwargs={'object_pairs_hook': collections.OrderedDict},
        dump_kwargs={'indent': 4, 'cls': JSONEncoder, 'separators': (',', ':')},
        help_text=_(
            "Query parameters which will be used to filter the discovery service's search/all endpoint results, "
            "specified as a JSON object. An empty JSON object means that all available content items will be "
            "included in the catalog.  Must be unique."
        ),
        validators=[validate_content_filter_fields]
    )
    uuid = models.UUIDField(
        unique=True,
        blank=False,
        null=False,
        default=uuid4,
    )
    include_exec_ed_2u_courses = models.BooleanField(
        default=False,
        help_text=_(
            "Specifies whether the catalog is allowed to include exec ed (2U) courses.  This means that, "
            "when the content_filter specifies that 'course' content types should be included in the catalog, "
            "executive-education-2u course types won't be excluded from the content of the associated catalog."
        ),
    )

    class Meta:
        verbose_name = _("Enterprise Catalog Query")
        verbose_name_plural = _("Enterprise Catalog Queries")
        app_label = 'enterprise'
        ordering = ['created']


class EnterpriseCustomerCatalog(TimeStampedModel):
    """
    Store catalog information from course discovery specifically for Enterprises.

    We use this model to consolidate course catalog information, which includes
    information about catalogs, courses, programs, and possibly more in the
    future, as the course discovery service evolves.

    .. no_pii:
    """

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False
    )
    title = models.CharField(
        default='All Content',
        max_length=255,
        blank=False,
        null=False
    )
    enterprise_customer = models.ForeignKey(
        EnterpriseCustomer,
        blank=False,
        null=False,
        related_name='enterprise_customer_catalogs',
        on_delete=models.deletion.CASCADE
    )
    enterprise_catalog_query = models.ForeignKey(
        EnterpriseCatalogQuery,
        blank=True,
        null=True,
        related_name='enterprise_customer_catalogs',
        on_delete=models.deletion.SET_NULL
    )
    content_filter = JSONField(
        default={},
        blank=True,
        null=True,
        load_kwargs={'object_pairs_hook': collections.OrderedDict},
        dump_kwargs={'indent': 4, 'cls': JSONEncoder, 'separators': (',', ':')},
        help_text=_(
            "Query parameters which will be used to filter the discovery service's search/all endpoint results, "
            "specified as a Json object. An empty Json object means that all available content items will be "
            "included in the catalog."
        ),
        validators=[validate_content_filter_fields]
    )
    enabled_course_modes = JSONField(
        default=json_serialized_course_modes,
        help_text=_('Ordered list of enrollment modes which can be displayed to learners for course runs in'
                    ' this catalog.'),
    )
    publish_audit_enrollment_urls = models.BooleanField(
        default=False,
        help_text=_(
            "Specifies whether courses should be published with direct-to-audit enrollment URLs."
        )
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Enterprise Customer Catalog")
        verbose_name_plural = _("Enterprise Customer Catalogs")
        app_label = 'enterprise'
        ordering = ['created']


class EnterpriseCustomerUser(TimeStampedModel):
    """
    Model that keeps track of user - enterprise customer affinity.

    Fields:
        enterprise_customer (ForeignKey[:class:`.EnterpriseCustomer`]): enterprise customer
        user_id (:class:`django.db.models.IntegerField`): user identifier

    .. no_pii:
    """

    enterprise_customer = models.ForeignKey(
        EnterpriseCustomer,
        blank=False,
        null=False,
        related_name='enterprise_customer_users',
        on_delete=models.deletion.CASCADE
    )
    user_id = models.PositiveIntegerField(null=False, blank=False, db_index=True)
    active = models.BooleanField(default=True)

    class Meta:
        app_label = 'enterprise'
        verbose_name = _("Enterprise Customer Learner")
        unique_together = (("enterprise_customer", "user_id"),)


class EnterpriseCourseEnrollment(TimeStampedModel):
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

    class Meta:
        unique_together = (('enterprise_customer_user', 'course_id',),)
        app_label = 'enterprise'

    enterprise_customer_user = models.ForeignKey(
        EnterpriseCustomerUser,
        blank=False,
        null=False,
        related_name='enterprise_enrollments',
        on_delete=models.deletion.CASCADE,
        help_text=_(
            "The enterprise learner to which this enrollment is attached."
        )
    )
    course_id = models.CharField(
        max_length=255,
        blank=False,
        help_text=_(
            "The ID of the course in which the learner was enrolled."
        )
    )

    @classmethod
    def get_enterprise_uuids_with_user_and_course(cls, user_id, course_run_id):
        """
        Returns a list of UUID(s) for EnterpriseCustomer(s) that this enrollment
        links together with the user_id and course_run_id
        """
        try:
            queryset = cls.objects.filter(
                course_id=course_run_id,
                enterprise_customer_user__user_id=user_id,
            )

            linked_enrollments = queryset.select_related(
                'enterprise_customer_user',
                'enterprise_customer_user__enterprise_customer',
            )
            return [str(le.enterprise_customer_user.enterprise_customer.uuid) for le in linked_enrollments]

        except ObjectDoesNotExist:
            return []
