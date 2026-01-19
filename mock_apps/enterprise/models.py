
import collections
import itertools
import logging
import json
from uuid import uuid4

from django.db import IntegrityError, models
from django.contrib.sites.models import Site
from django.contrib.sites.shortcuts import get_current_site
from django.utils.translation import gettext_lazy as _
from django.utils.functional import cached_property
from django.contrib import auth
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings

from model_utils.models import TimeStampedModel
from django_countries.fields import CountryField
from edx_rbac.models import UserRole, UserRoleAssignment
from jsonfield.encoder import JSONEncoder
from jsonfield.fields import JSONField
from slumber.exceptions import HttpClientError

from enterprise import utils
from enterprise.api_client.lms import EnrollmentApiClient, ThirdPartyAuthApiClient
from enterprise.utils import get_enterprise_worker_user, get_user_valid_idp, CourseEnrollmentDowngradeError, CourseEnrollmentPermissionError
from enterprise.constants import json_serialized_course_modes, ALL_ACCESS_CONTEXT
from enterprise.validators import validate_content_filter_fields


try:
    from common.djangoapps.student.models import CourseEnrollment
except ImportError:
    CourseEnrollment = None

User = auth.get_user_model()
LOGGER = logging.getLogger(__name__)


class EnterpriseCustomerManager(models.Manager):
    """
    Model manager for :class:`.EnterpriseCustomer` model.

    Filters out inactive Enterprise Customers, otherwise works the same as default model manager.
    """

    # This manager filters out some records, hence according to the Django docs it must not be used
    # for related field access. Although False is default value, it still makes sense to set it explicitly
    # https://docs.djangoproject.com/en/1.10/topics/db/managers/#base-managers
    use_for_related_fields = False

    def get_queryset(self):
        """
        Return a new QuerySet object. Filters out inactive Enterprise Customers.
        """
        return super().get_queryset().filter(active=True)


class EnterpriseCustomerCatalog(TimeStampedModel):
    """
    Store catalog information from course discovery specifically for Enterprises.
    """
    title = models.CharField(max_length=255, blank=False, null=False)
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    enterprise_customer = models.ForeignKey(
        'enterprise.EnterpriseCustomer',
        related_name='ep_customer_catalogs',
        on_delete=models.deletion.CASCADE
    )
    enterprise_catalog_query = models.ForeignKey(
        'enterprise.EnterpriseCatalogQuery',
        related_name='ep_customer_catalog_query',
        on_delete=models.deletion.CASCADE
    )
    content_filter = JSONField(
        default={},
        blank=True,
        null=True,
        load_kwargs={'object_pairs_hook': collections.OrderedDict},
        dump_kwargs={'indent': 4, 'cls': JSONEncoder, 'separators': (',', ':')},
        validators=[validate_content_filter_fields]
    )
    enabled_course_modes = JSONField(default=json_serialized_course_modes)
    publish_audit_enrollment_urls = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("Enterprise Customer Catalog")
        verbose_name_plural = _("Enterprise Customer Catalogs")
        app_label = 'enterprise'
        ordering = ['created']


class EnterpriseCourseEnrollment(models.Model):
    """
    Store information about the enrollment of a user in a course.
    """
    course_id = models.CharField(max_length=255, blank=False, null=False)
    saved_for_later = models.BooleanField(default=False)
    enterprise_customer_user = models.ForeignKey(
        'enterprise.EnterpriseCustomerUser',
        related_name='enterprise_enrollments',
        on_delete=models.deletion.CASCADE
    )

    @property
    def audit_reporting_disabled(self):
        """
        Specify whether audit track data reporting is disabled for this enrollment.

        * If the enterprise customer associated with this enrollment enables audit track data reporting,
          simply return False.
        * If the enterprise customer associated with this enrollment does not enable audit track data reporting,
          return True if we are dealing with an audit enrollment, and False otherwise.

        :return: True if audit track data reporting is disabled, False otherwise.
        """
        if not self.enterprise_customer_user.enterprise_customer.enables_audit_data_reporting:
            return self.is_audit_enrollment

        # Since audit data reporting is enabled, we always return False here.
        return False

    @property
    def is_audit_enrollment(self):
        """
        Specify whether the course enrollment associated with this ``EnterpriseCourseEnrollment`` is in audit mode.

        :return: Whether the course enrollment mode is of an audit type.
        """

        course_enrollment = self.course_enrollment

        audit_modes = getattr(settings, 'ENTERPRISE_COURSE_ENROLLMENT_AUDIT_MODES', ['audit', 'honor'])
        return course_enrollment and (course_enrollment.mode in audit_modes)

    @cached_property
    def course_enrollment(self):
        """
        Returns the ``student.CourseEnrollment`` associated with this enterprise course enrollment record.
        """
        if not CourseEnrollment:
            return None
        try:
            return CourseEnrollment.objects.get(
                user=self.enterprise_customer_user.user,
                course_id=self.course_id,
            )
        except CourseEnrollment.DoesNotExist:
            LOGGER.error('{} does not have a matching student.CourseEnrollment'.format(self))
            return None

    @classmethod
    def get_enterprise_course_enrollment_id(cls, user, course_id, enterprise_customer):
        """
        Return the EnterpriseCourseEnrollment object for a given user in given course_id.
        """
        enterprise_course_enrollment_id = None
        try:
            enterprise_course_enrollment_id = cls.objects.get(
                enterprise_customer_user=EnterpriseCustomerUser.objects.get(
                    enterprise_customer=enterprise_customer,
                    user_id=user.id
                ),
                course_id=course_id
            ).id
        except ObjectDoesNotExist:
            LOGGER.info(
                'EnterpriseCourseEnrollment entry not found for user: {username}, course: {course_id}, '
                'enterprise_customer: {enterprise_customer_name}'.format(
                    username=user.username,
                    course_id=course_id,
                    enterprise_customer_name=enterprise_customer.name
                )
            )
        return enterprise_course_enrollment_id

    @classmethod
    def get_enterprise_uuids_with_user_and_course(cls, user_id, course_run_id, is_customer_active=None):
        """
        Returns a list of UUID(s) for EnterpriseCustomer(s) that this enrollment
        links together with the user_id and course_run_id
        """
        try:
            queryset = cls.objects.filter(
                course_id=course_run_id,
                enterprise_customer_user__user_id=user_id,
            )
            if is_customer_active is not None:
                queryset = queryset.filter(
                    enterprise_customer_user__enterprise_customer__active=is_customer_active,
                )

            linked_enrollments = queryset.select_related(
                'enterprise_customer_user',
                'enterprise_customer_user__enterprise_customer',
            )
            return [str(le.enterprise_customer_user.enterprise_customer.uuid) for le in linked_enrollments]

        except ObjectDoesNotExist:
            LOGGER.info(
                'EnterpriseCustomerUser entries not found for user id: {username}, course: {course_run_id}.'
                .format(
                    username=user_id,
                    course_run_id=course_run_id,
                )
            )
            return []

    class Meta:
        app_label = 'enterprise'


class EnterpriseCustomer(TimeStampedModel):
    enterprise_customer_catalogs = models.ManyToManyField(
    EnterpriseCustomerCatalog,
    verbose_name="Enterprise Customer Catalogs",
    )
    AT_ENROLLMENT = 'at_enrollment'
    EXTERNALLY_MANAGED = 'externally_managed'
    DATA_SHARING_CONSENT_CHOICES = (
        (AT_ENROLLMENT, 'At Enrollment'),
        (EXTERNALLY_MANAGED, 'Managed externally')
    )

    objects = models.Manager()
    active_customers = EnterpriseCustomerManager()

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
    country = CountryField(null=True)
    site = models.ForeignKey(
        Site,
        related_name="enterprise_customers",
        default=get_current_site,
        on_delete=models.deletion.CASCADE
    )
    hide_course_original_price = models.BooleanField(
        "Hide course price on learning platform",
        default=False,
    )
    enable_data_sharing_consent = models.BooleanField(
        verbose_name="Activate data sharing consent prompt",
        default=False,
    )
    enforce_data_sharing_consent = models.CharField(
        verbose_name="Data sharing consent enforcement:",
        max_length=25,
        blank=False,
        choices=DATA_SHARING_CONSENT_CHOICES,
        default=AT_ENROLLMENT,
    )
    enable_audit_enrollment = models.BooleanField(
        verbose_name="Enable audit enrollment for learning platform learners",
        default=False,
    )
    enable_audit_data_reporting = models.BooleanField(
        verbose_name="Enable audit enrollment data reporting for learning platform learners",
        default=False,
    )
    contact_email = models.EmailField(
        verbose_name="Customer admin contact email:",
        null=True,
        blank=True,
    )
    default_language = models.CharField(
        verbose_name="Learner default language",
        max_length=25,
        null=True,
        blank=True,
        default=None,
    )
    sender_alias = models.CharField(
        verbose_name="Automated email sender alias",
        max_length=255,
        null=True,
        blank=True,
    )
    reply_to = models.EmailField(
        verbose_name="Customer “reply to” email:",
        null=True,
        blank=True,
    )
    hide_labor_market_data = models.BooleanField(
        verbose_name="Hide labor market data on skill features",
        default=False,
    )
    auth_org_id = models.CharField(max_length=80, blank=True, null=True)
    enable_generation_of_api_credentials = models.BooleanField(
        verbose_name="Allow generation of API credentials",
        default=False,
    )
    learner_portal_sidebar_content = models.TextField(blank=True)

    @property
    def enables_audit_data_reporting(self):
        """
        Determine whether the enterprise customer has enabled the ability to report/pass-back audit track data.
        """
        return self.enable_audit_enrollment and self.enable_audit_data_reporting

    @property
    def identity_provider(self):
        """
        Return the first identity provider id associated with this enterprise customer.
        """
        # pylint: disable=no-member
        identity_provider = self.enterprise_customer_identity_providers.first()
        if identity_provider:
            return identity_provider.provider_id
        LOGGER.info("No linked identity provider found for enterprise customer: %s", self.uuid)
        return None

    @property
    def has_identity_providers(self):
        """
        Return True if there are any identity providers associated with this enterprise customer.
        """
        return self.enterprise_customer_identity_providers.exists()

    @property
    def has_multiple_idps(self):
        """
        Return True if there are multiple identity providers associated with this enterprise customer.
        """
        return self.enterprise_customer_identity_providers.count() > 1

    class Meta:
        app_label = 'enterprise'
        verbose_name = _("Enterprise Customer")
        verbose_name_plural = _("Enterprise Customers")


class AdminNotification(models.Model):
    
    class Meta:
        app_label = 'enterprise'



class DefaultEnterpriseEnrollmentIntention(models.Model):
    COURSE = 'course'

    class Meta:
        app_label = 'enterprise'


class EnrollmentNotificationEmailTemplate(models.Model):

    class Meta:
        app_label = 'enterprise'


class EnterpriseCatalogQuery(models.Model):
    title = models.CharField(max_length=255, blank=False, null=False)
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)

    class Meta:
        app_label = 'enterprise'


class EnterpriseCustomerBrandingConfiguration(models.Model):
    
    class Meta:
        app_label = 'enterprise'


class EnterpriseCustomerIdentityProvider(models.Model):
    enterprise_customer = models.ForeignKey(
        EnterpriseCustomer,
        related_name='enterprise_customer_identity_providers',
        on_delete=models.deletion.CASCADE
    )
    provider_id = models.SlugField(max_length=255, blank=False, null=False)
    default_provider = models.BooleanField(default=False)

    class Meta:
        app_label = 'enterprise'


class EnterpriseCustomerInviteKey(models.Model):
    
    class Meta:
        app_label = 'enterprise'


class EnterpriseCustomerReportingConfiguration(models.Model):
    
    class Meta:
        app_label = 'enterprise'


class EnterpriseCustomerSsoConfiguration(models.Model):
    
    class Meta:
        app_label = 'enterprise'


class EnterpriseCustomerUserManager(models.Manager):
    """
    Model manager for :class:`.EnterpriseCustomerUser` entity.

    This class should contain methods that create, modify or query :class:`.EnterpriseCustomerUser` entities.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize custom manager.

        kwargs:
            linked_only (Bool): create a manager with linked learners only if True else all(linked and unlinked) records
        """
        self.linked_only = kwargs.pop('linked_only', True)
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        """
        Return linked or unlinked learners based on how the manager is created.
        """
        if self.linked_only:
            return super().get_queryset().filter(linked=True)

        return super().get_queryset()

    def unlink_user(self, enterprise_customer, user_email, is_relinkable=True):
        """
        Unlink user email from Enterprise Customer.

        If :class:`django.contrib.auth.models.User` instance with specified email does not exist,
        :class:`.PendingEnterpriseCustomerUser` instance is deleted instead.

        Raises EnterpriseCustomerUser.DoesNotExist if instance of :class:`django.contrib.auth.models.User` with
        specified email exists and corresponding :class:`.EnterpriseCustomerUser` instance does not.

        Raises PendingEnterpriseCustomerUser.DoesNotExist exception if instance of
        :class:`django.contrib.auth.models.User` with specified email exists and corresponding
        :class:`.PendingEnterpriseCustomerUser` instance does not.
        """
        try:
            existing_user = User.objects.get(email=user_email)
            # not capturing DoesNotExist intentionally to signal to view that link does not exist
            link_record = self.get(enterprise_customer=enterprise_customer, user_id=existing_user.id)
            link_record.linked = False
            link_record.active = False
            # If is_relinkable = False, user will be permanently be unlinked from the enterprise
            link_record.is_relinkable = is_relinkable
            link_record.save()
        except User.DoesNotExist:
            # not capturing DoesNotExist intentionally to signal to view that link does not exist
            pending_link = PendingEnterpriseCustomerUser.objects.get(
                enterprise_customer=enterprise_customer, user_email=user_email
            )
            pending_link.delete()

        LOGGER.info(
            'Enterprise learner {%s} successfully unlinked from Enterprise Customer {%s}',
            user_email,
            enterprise_customer.name
        )


class EnterpriseCustomerUser(TimeStampedModel):

    enterprise_customer = models.ForeignKey(
        EnterpriseCustomer,
        blank=False,
        null=False,
        related_name='enterprise_customer_users',
        on_delete=models.deletion.CASCADE
    )

    objects = EnterpriseCustomerUserManager()
    all_objects = EnterpriseCustomerUserManager(linked_only=False)

    user_id = models.PositiveIntegerField(null=False, blank=False, db_index=True)
    active = models.BooleanField(default=True)
    linked = models.BooleanField(default=False)
    is_relinkable = models.BooleanField(default=True)
    invite_key = models.ForeignKey(
        EnterpriseCustomerInviteKey,
        blank=True,
        null=True,
        on_delete=models.deletion.SET_NULL
    )

    @property
    def user(self):
        """
        Return User associated with this instance.

        Return :class:`django.contrib.auth.models.User` instance associated with this
        :class:`EnterpriseCustomerUser` instance via email.
        """
        try:
            return User.objects.get(pk=self.user_id)
        except User.DoesNotExist:
            return None

    @property
    def username(self):
        """
        Return linked user's username.
        """
        if self.user is not None:
            return self.user.username
        return None

    @property
    def user_email(self):
        """
        Return linked user email.
        """
        if self.user is not None:
            return self.user.email
        return None

    def get_remote_id(self, idp_id=None):
        """
        Retrieve the SSO provider's identifier for this user from the LMS Third Party API.
        In absence of idp_id, returns id from default idp

        Arguments:
            idp_id (str) (optional): If provided, idp resolution skipped and specified idp used
                to locate remote id.

        Returns None if:
        * the user doesn't exist, or
        * the associated EnterpriseCustomer has no identity_provider, or
        * the remote identity is not found.
        """
        user = self.user
        if idp_id:
            enterprise_worker = get_enterprise_worker_user()
            client = ThirdPartyAuthApiClient(enterprise_worker)
            return client.get_remote_id(idp_id, user.username)
        if user and self.enterprise_customer.has_identity_providers:
            identity_provider = None
            if self.enterprise_customer.has_multiple_idps:
                identity_provider = get_user_valid_idp(self.user, self.enterprise_customer)

            if not identity_provider:
                identity_provider = self.enterprise_customer.identity_provider

            enterprise_worker = get_enterprise_worker_user()
            client = ThirdPartyAuthApiClient(enterprise_worker)
            return client.get_remote_id(identity_provider, user.username)
        return None

    def enroll(self, course_run_id, mode, cohort=None, source_slug=None, discount_percentage=0.0, sales_force_id=None):
        """
        Enroll a user into a course track, and register an enterprise course enrollment.
        """
        enrollment_api_client = EnrollmentApiClient()
        # Check to see if the user's already enrolled and we have an enterprise course enrollment to track it.
        course_enrollment = enrollment_api_client.get_course_enrollment(self.username, course_run_id) or {}
        enrolled_in_course = course_enrollment and course_enrollment.get('is_active', False)

        audit_modes = getattr(settings, 'ENTERPRISE_COURSE_ENROLLMENT_AUDIT_MODES', ['audit', 'honor'])
        paid_modes = ['verified', 'professional']
        is_upgrading = mode in paid_modes and course_enrollment.get('mode') in audit_modes

        if enrolled_in_course and is_upgrading:
            LOGGER.info(
                "[Enroll] Trying to upgrade the enterprise customer user [{ecu_id}] in course [{course_run_id}] in "
                "[{mode}] mode".format(
                    ecu_id=self.id,
                    course_run_id=course_run_id,
                    mode=mode,
                )
            )
        if not enrolled_in_course:
            LOGGER.info(
                "[Enroll] Trying to enroll the enterprise customer user [{ecu_id}] in course [{course_run_id}] in "
                "[{mode}] mode".format(
                    ecu_id=self.id,
                    course_run_id=course_run_id,
                    mode=mode,
                )
            )

        if not enrolled_in_course or is_upgrading:
            if cohort and not self.enterprise_customer.enable_autocohorting:
                raise CourseEnrollmentPermissionError("Auto-cohorting is not enabled for this enterprise")

            # Directly enroll into the specified track.
            succeeded = True
            LOGGER.info(
                "[Enroll] Calling LMS enrollment API for user {username} in course {course_run_id} in "
                " mode {mode}".format(
                    username=self.username,
                    course_run_id=course_run_id,
                    mode=mode,
                )
            )
            try:
                enrollment_api_client.enroll_user_in_course(
                    self.username,
                    course_run_id,
                    mode,
                    cohort=cohort,
                    enterprise_uuid=str(self.enterprise_customer.uuid)
                )
            except HttpClientError as exc:
                succeeded = False
                default_message = 'No error message provided'
                try:
                    error_message = json.loads(exc.content.decode()).get('message', default_message)
                except ValueError:
                    error_message = default_message
                LOGGER.exception(
                    'Error while enrolling user %(user)s: %(message)s',
                    {'user': self.user_id, 'message': error_message},
                )

            if succeeded:
                LOGGER.info(
                    "[Enroll] LMS enrollment API succeeded for user {username} in course {course_run_id} in "
                    " mode {mode}".format(
                        username=self.username,
                        course_run_id=course_run_id,
                        mode=mode,
                    )
                )
                try:
                    EnterpriseCourseEnrollment.objects.get_or_create(
                        enterprise_customer_user=self,
                        course_id=course_run_id,
                        defaults={
                            'source': EnterpriseEnrollmentSource.get_source(source_slug)
                        }
                    )
                    LOGGER.info(
                        "EnterpriseCourseEnrollment created for enterprise customer user %s and course id %s",
                        self.id, course_run_id,
                    )
                except IntegrityError:
                    # Added to try and fix ENT-2463. This can happen if the user is already a part of the enterprise
                    # because of the following:
                    # 1. (non-enterprise) CourseEnrollment data is created
                    # 2. An async task to is signaled to run after CourseEnrollment creation
                    #    (create_enterprise_enrollment_receiver)
                    # 3. Both async task and the code in the try block run `get_or_create` on
                    # `EnterpriseCourseEnrollment`
                    # 4. A race condition happens and it tries to create the same data twice
                    # Catching will allow us to continue and ensure we can still create an order for this enrollment.
                    LOGGER.exception(
                        "IntegrityError on attempt at EnterpriseCourseEnrollment for user with id [%s] "
                        "and course id [%s]", self.user_id, course_run_id,
                    )

                if mode in paid_modes:
                    # create an ecommerce order for the course enrollment
                    self.create_order_for_enrollment(course_run_id, discount_percentage, mode, sales_force_id)

                utils.track_event(self.user_id, 'edx.bi.user.enterprise.enrollment.course', {
                    'category': 'enterprise',
                    'label': course_run_id,
                    'enterprise_customer_uuid': str(self.enterprise_customer.uuid),
                    'enterprise_customer_name': self.enterprise_customer.name,
                    'mode': mode,
                    'cohort': cohort,
                    'is_upgrading': is_upgrading,
                })
        elif enrolled_in_course and course_enrollment.get('mode') in paid_modes and mode in audit_modes:
            # This enrollment is attempting to "downgrade" the user from a paid track they are already in.
            raise CourseEnrollmentDowngradeError(
                'The user is already enrolled in the course {course_run_id} in {current_mode} mode '
                'and cannot be enrolled in {given_mode} mode'.format(
                    course_run_id=course_run_id,
                    current_mode=course_enrollment.get('mode'),
                    given_mode=mode,
                )
            )

    def unenroll(self, course_run_id):
        """
        Unenroll a user from a course track.
        """
        enrollment_api_client = EnrollmentApiClient()
        if enrollment_api_client.unenroll_user_from_course(self.username, course_run_id):
            EnterpriseCourseEnrollment.objects.filter(enterprise_customer_user=self, course_id=course_run_id).delete()
            return True
        return False

    class Meta:
        app_label = 'enterprise'


class EnterpriseFeatureRole(models.Model):
    
    class Meta:
        app_label = 'enterprise'


class EnterpriseFeatureUserRoleAssignment(models.Model):
    
    class Meta:
        app_label = 'enterprise'


class EnterpriseGroup(models.Model):
    
    class Meta:
        app_label = 'enterprise'


class EnterpriseGroupMembership(models.Model):
    
    class Meta:
        app_label = 'enterprise'


class LearnerCreditEnterpriseCourseEnrollment(models.Model):
    
    class Meta:
        app_label = 'enterprise'


class LicensedEnterpriseCourseEnrollment(models.Model):
    
    class Meta:
        app_label = 'enterprise'


class PendingEnrollment(models.Model):
    
    class Meta:
        app_label = 'enterprise'


class PendingEnterpriseCustomerAdminUser(models.Model):
    
    class Meta:
        app_label = 'enterprise'


class PendingEnterpriseCustomerUser(models.Model):
    
    class Meta:
        app_label = 'enterprise'


class SystemWideEnterpriseRole(UserRole):
    pass


class SystemWideEnterpriseUserRoleAssignment(UserRoleAssignment):

    role = models.ForeignKey(
        SystemWideEnterpriseRole,
        related_name="system_wide_role_assignments",
        on_delete=models.CASCADE,
    )

    @classmethod
    def get_distinct_assignments_by_role_name(cls, user, role_names=None):
        """
        Returns a mapping of role names to sets of enterprise customer uuids
        for which the user is assigned that role.
        """
        # super().get_assignments() returns pairs of (role name, contexts), where
        # contexts is a list of 0 or more enterprise uuids (or the ALL_ACCESS_CONTEXT token)
        # as returned from super().get_context().
        # To make matters worse, get_context() could return null, meaning the role
        # applies to any context.  So we should still include it in the list of "customers"
        # for a given role.
        # See https://openedx.atlassian.net/browse/ENT-4346 for outstanding technical debt
        # related to this issue.
        assigned_customers_by_role = collections.defaultdict(set)
        for role_name, customer_uuids in super().get_assignments(user, role_names):
            if customer_uuids is not None:
                assigned_customers_by_role[role_name].update(customer_uuids)
            else:
                assigned_customers_by_role[role_name].add(None)
        return assigned_customers_by_role

    @classmethod
    def get_assignments(cls, user, role_names=None):
        """
        Return an iterator of (rolename, [enterprise customer uuids]) for the given
        user (and maybe role_names).

        Differs from super().get_assignments(...) in that it yields (role name, customer uuid list) pairs
        such that the first item in the customer uuid list for each role
        corresponds to the currently *active* EnterpriseCustomerUser for the user.

        The resulting generated pairs are sorted by role name, and within role_name, by (active, customer uuid).
        For example:

          ('enterprise_admin', ['active-enterprise-uuid', 'inactive-enterprise-uuid', 'other-inactive-enterprise-uuid'])
          ('enterprise_learner', ['active-enterprise-uuid', 'inactive-enterprise-uuid']),
          ('enterprise_openedx_operator', ['*'])
        """
        customers_by_role = cls.get_distinct_assignments_by_role_name(user, role_names)
        if not customers_by_role:
            return

        # Filter for a set of only the *active* enterprise uuids for which the user is assigned a role.
        # A user should typically only have one active enterprise user at a time, but we'll
        # use sets to cover edge cases.
        all_customer_uuids_for_user = set(itertools.chain(*customers_by_role.values()))

        # ALL_ACCESS_CONTEXT is not a value UUID on which to filter enterprise customer uuids.
        all_customer_uuids_for_user.discard(ALL_ACCESS_CONTEXT)

        active_enterprise_uuids_for_user = set(
            str(customer_uuid) for customer_uuid in
            EnterpriseCustomerUser.get_active_enterprise_users(
                user.id,
                enterprise_customer_uuids=all_customer_uuids_for_user,
            ).values_list('enterprise_customer', flat=True)
        )

        for role_name in sorted(customers_by_role):
            customer_uuids_for_role = customers_by_role[role_name]

            # Determine the *active* enterprise uuids assigned for this role.
            active_enterprises_for_role = sorted(
                customer_uuids_for_role.intersection(active_enterprise_uuids_for_user)
            )
            # Determine the *inactive* enterprise uuids assigned for this role,
            # could include the ALL_ACCESS_CONTEXT token.
            inactive_enterprises_for_role = sorted(
                customer_uuids_for_role.difference(active_enterprise_uuids_for_user)
            )
            ordered_enterprises = active_enterprises_for_role + inactive_enterprises_for_role

            # Sometimes get_context() returns ``None``, and ``None`` is a meaningful downstream value
            # to the consumers of get_assignments(), either
            # when constructing JWT roles or when checking for explicit or implicit access to some context.
            # So if the only unique thing returned by get_context() for this role was ``None``,
            # we should unpack it from the list before yielding.
            # See https://openedx.atlassian.net/browse/ENT-4346 for outstanding technical debt
            # related to this issue.
            if ordered_enterprises == [None]:
                yield (role_name, None)
            else:
                yield (role_name, ordered_enterprises)

    class Meta:
        app_label = 'enterprise'


class EnterpriseEnrollmentSource(TimeStampedModel):
    """
    Define a Name and Source for all Enterprise Enrollment Sources.

    .. no_pii:
    """

    MANUAL = 'manual'
    API = 'enterprise_api'
    CUSTOMER_ADMIN = 'customer_admin'
    ENROLLMENT_URL = 'enrollment_url'
    OFFER_REDEMPTION = 'offer_redemption'
    ENROLLMENT_TASK = 'enrollment_task'
    MANAGEMENT_COMMAND = 'management_command'

    name = models.CharField(max_length=64)
    slug = models.SlugField(max_length=30, unique=True)

    @classmethod
    def get_source(cls, source_slug):
        """
        Retrieve the source based on the Slug provided.
        """
        try:
            return cls.objects.get(slug=source_slug)
        except EnterpriseEnrollmentSource.DoesNotExist:
            return None

    def __str__(self):
        """
        Create string representation of the source.
        """
        return "Enrollment Source: {name}, Slug: {slug}".format(name=self.name, slug=self.slug)


class BulkCatalogQueryUpdateCommandConfiguration(models.Model):
    """Minimal stub configuration model required for admin imports in tests."""

    class Meta:
        app_label = 'enterprise'
