import logging

from django.db import models
from django.core.exceptions import ImproperlyConfigured

from enterprise.models import EnterpriseCustomer
from enterprise.api_client.discovery import get_course_catalog_api_service_client

LOGGER = logging.getLogger(__name__)

class DataSharingConsentQuerySet(models.query.QuerySet):
    """
    Customized QuerySets for the ``DataSharingConsent`` model.

    When searching for any ``DataSharingConsent`` object, if it doesn't exist, return a single
    ``ProxyDataSharingConsent`` object which behaves just like a ``DataSharingConsent`` object
    except is not saved in the database until committed.
    """

    def proxied_get(self, *args, **kwargs):
        """
        Perform the query and returns a single object matching the given keyword arguments.

        This customizes the queryset to return an instance of ``ProxyDataSharingConsent`` when
        the searched-for ``DataSharingConsent`` instance does not exist.
        """
        original_kwargs = kwargs.copy()
        if 'course_id' in kwargs:
            try:
                # Try to get the record for the course OR course run, depending on what we got in kwargs,
                # course_id or course_run_id
                return self.get(*args, **kwargs)
            except DataSharingConsent.DoesNotExist:
                # If here, either the record for course OR course run doesn't exist.
                # Try one more time by modifying the query parameters to look for just a course record this time.
                site = None
                if 'enterprise_customer' in kwargs:
                    site = kwargs['enterprise_customer'].site

                try:
                    course_id = get_course_catalog_api_service_client(site=site).get_course_id(
                        course_identifier=kwargs['course_id']
                    )
                    kwargs['course_id'] = course_id
                except ImproperlyConfigured:
                    LOGGER.warning('CourseCatalogApiServiceClient is improperly configured.')

        try:
            # Try to get the record of course
            return self.get(*args, **kwargs)
        except DataSharingConsent.DoesNotExist:
            # If here, the record doesn't exist for course AND course run, so return a proxy record instead.
            return ProxyDataSharingConsent(**original_kwargs)

class DataSharingConsentManager(models.Manager.from_queryset(DataSharingConsentQuerySet)):
    """
    Model manager for :class:`.DataSharingConsent` model.

    Uses a QuerySet that returns a ``ProxyDataSharingConsent`` object when the searched-for
    ``DataSharingConsent`` object does not exist. Otherwise behaves the same as a normal manager.
    """


class ProxyDataSharingConsent:
    """
    A proxy-model of the ``DataSharingConsent`` model; it's not a real model, but roughly behaves like one.

    Upon commit, a real ``DataSharingConsent`` object which mirrors the ``ProxyDataSharingConsent`` object's
    pseudo-model-fields is created, returned, and saved in the database. The remnant, in-heap
    ``ProxyDataSharingConsent`` object may be deleted afterwards, but if not, its ``exists`` fields remains ``True``
    to indicate that the object has been committed.

    NOTE: This class will be utilized when we implement program level consent by having an abstraction over these
          consent objects per course.
    """

    objects = DataSharingConsentManager()

    def __init__(
            self,
            enterprise_customer=None,
            username='',
            course_id='',
            program_uuid='',
            granted=False,
            exists=False,
            child_consents=None,
            **kwargs
    ):
        """
        Initialize a proxy version of ``DataSharingConsent`` which behaves similarly but does not exist in the DB.
        """
        ec_keys = {}
        for key, value in kwargs.items():
            if str(key).startswith('enterprise_customer__'):
                enterprise_customer_detail = key[len('enterprise_customer__'):]
                ec_keys[enterprise_customer_detail] = value

        if ec_keys:
            enterprise_customer = EnterpriseCustomer.objects.get(**ec_keys)

        self.enterprise_customer = enterprise_customer
        self.username = username
        self.course_id = course_id
        self.program_uuid = program_uuid
        self.granted = granted
        self._exists = exists
        self._child_consents = child_consents or []


class DataSharingConsent(models.Model):
    """
    An abstract representation of Data Sharing Consent granted to an Enterprise for a course by a User.

    The model is used to store a persistent, historical consent state for users granting, not granting, or revoking
    data sharing consent to an Enterprise for a course.

    .. pii: The username field inherited from Consent contains PII.
    .. pii_types: username
    .. pii_retirement: consumer_api
    """
    enterprise_customer = models.ForeignKey(
        EnterpriseCustomer,
        on_delete=models.CASCADE,
        related_name='data_sharing_consent',
    )
    username = models.CharField(max_length=255)
    course_id = models.CharField(max_length=255)
    granted = models.BooleanField(default=True)

    objects = DataSharingConsentManager()

    class Meta:
        app_label = 'consent'


class DataSharingConsentTextOverrides(models.Model):

    enterprise_customer = models.ForeignKey(
        EnterpriseCustomer,
        on_delete=models.CASCADE,
        related_name='data_sharing_consent_text_overrides',
    )
    published = models.BooleanField(default=True)
    
    class Meta:
        app_label = 'consent'
