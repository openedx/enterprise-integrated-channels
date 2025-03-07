from uuid import uuid4

from django.db import models
from django.contrib.sites.models import Site
from django.contrib.sites.shortcuts import get_current_site
from django.utils.translation import gettext_lazy as _

from model_utils.models import TimeStampedModel
from django_countries.fields import CountryField


class EnterpriseCustomerCatalog(models.Model):
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
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Enterprise Customer Catalog")
        verbose_name_plural = _("Enterprise Customer Catalogs")
        app_label = 'enterprise'
        ordering = ['created']


class EnterpriseCourseEnrollment(models.Model):
    """
    Store information about the enrollment of a user in a course.
    """

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
        related_name="ep_cs_site",
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


class EnterpriseCustomerUser(models.Model):
    
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


class SystemWideEnterpriseUserRoleAssignment(models.Model):
    
    class Meta:
        app_label = 'enterprise'