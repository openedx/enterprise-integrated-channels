"""
Database models for enterprise.
"""
from django.db import models


class EnterpriseCustomerCatalog:
    """
    Store catalog information from course discovery specifically for Enterprises.
    """


class EnterpriseCourseEnrollment:
    """
    Store information about the enrollment of a user in a course.
    """


class EnterpriseCustomer:
    enterprise_customer_catalogs = models.ManyToManyField(
    EnterpriseCustomerCatalog,
    verbose_name="Enterprise Customer Catalogs",
    )