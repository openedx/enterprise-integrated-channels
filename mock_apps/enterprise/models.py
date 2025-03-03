"""
Database models for enterprise.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _

class EnterpriseCustomerCatalog(models.Model):
    """
    Store catalog information from course discovery specifically for Enterprises.
    """

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


class EnterpriseCustomer(models.Model):
    enterprise_customer_catalogs = models.ManyToManyField(
    EnterpriseCustomerCatalog,
    verbose_name="Enterprise Customer Catalogs",
    )

    class Meta:
        app_label = 'enterprise'
        verbose_name = _("Enterprise Customer")
        verbose_name_plural = _("Enterprise Customers")


class AdminNotification(models.Model):
    
    class Meta:
        app_label = 'enterprise'



class DefaultEnterpriseEnrollmentIntention(models.Model):

    class Meta:
        app_label = 'enterprise'


class EnrollmentNotificationEmailTemplate(models.Model):

    class Meta:
        app_label = 'enterprise'


class EnterpriseCatalogQuery(models.Model):
    
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