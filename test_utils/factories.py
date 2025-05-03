"""
Factoryboy factories.
"""

from random import randint
from uuid import UUID

from datetime import timezone
from django.contrib import auth
from django.contrib.sites.models import Site

import factory
from faker import Factory as FakerFactory
from oauth2_provider.models import get_application_model

from consent.models import DataSharingConsent, DataSharingConsentTextOverrides
from enterprise.constants import FulfillmentTypes
from enterprise.models import (
    EnterpriseCatalogQuery,
    EnterpriseCourseEnrollment,
    EnterpriseCustomer,
    EnterpriseCustomerCatalog,
    EnterpriseCustomerIdentityProvider,
    EnterpriseCustomerUser,
    LearnerCreditEnterpriseCourseEnrollment,
)
from enterprise.utils import localized_utcnow
from channel_integrations.blackboard.models import (
    BlackboardEnterpriseCustomerConfiguration,
    BlackboardGlobalConfiguration,
)
from channel_integrations.canvas.models import CanvasEnterpriseCustomerConfiguration
from channel_integrations.cornerstone.models import (
    CornerstoneEnterpriseCustomerConfiguration,
    CornerstoneGlobalConfiguration,
    CornerstoneLearnerDataTransmissionAudit,
)
from channel_integrations.degreed2.models import Degreed2EnterpriseCustomerConfiguration

from channel_integrations.integrated_channel.models import (
    ContentMetadataItemTransmission,
    GenericEnterpriseCustomerPluginConfiguration,
    GenericLearnerDataTransmissionAudit,
    LearnerDataTransmissionAudit,
    OrphanedContentTransmissions,
)
from channel_integrations.moodle.models import MoodleEnterpriseCustomerConfiguration
from channel_integrations.sap_success_factors.models import (
    SAPSuccessFactorsEnterpriseCustomerConfiguration,
    SAPSuccessFactorsGlobalConfiguration,
    SapSuccessFactorsLearnerDataTransmissionAudit,
)
from channel_integrations.xapi.models import XAPILearnerDataTransmissionAudit, XAPILRSConfiguration

FAKER = FakerFactory.create()
User = auth.get_user_model()
Application = get_application_model()


# pylint: disable=no-member
class SiteFactory(factory.django.DjangoModelFactory):
    """
    Factory class for Site model.
    """

    class Meta:
        """
        Meta for ``SiteFactory``.
        """

        model = Site
        django_get_or_create = ("domain",)

    domain = factory.LazyAttribute(lambda x: FAKER.domain_name())
    name = factory.LazyAttribute(lambda x: FAKER.company())


class EnterpriseCustomerFactory(factory.django.DjangoModelFactory):
    """
    EnterpriseCustomer factory.

    Creates an instance of EnterpriseCustomer with minimal boilerplate - uses this class' attributes as default
    parameters for EnterpriseCustomer constructor.
    """

    class Meta:
        """
        Meta for EnterpriseCustomerFactory.
        """

        model = EnterpriseCustomer

    uuid = factory.LazyAttribute(lambda x: UUID(FAKER.uuid4()))
    name = factory.LazyAttribute(lambda x: FAKER.company())
    slug = factory.LazyAttribute(lambda x: FAKER.slug())
    active = True
    site = factory.SubFactory(SiteFactory)
    enable_data_sharing_consent = True
    enforce_data_sharing_consent = EnterpriseCustomer.AT_ENROLLMENT
    enable_audit_enrollment = False
    enable_audit_data_reporting = False
    hide_course_original_price = False
    country = 'US'
    contact_email = factory.LazyAttribute(lambda x: FAKER.email())
    default_language = 'en'
    sender_alias = factory.LazyAttribute(lambda x: FAKER.word())
    reply_to = factory.LazyAttribute(lambda x: FAKER.email())
    hide_labor_market_data = False
    auth_org_id = factory.LazyAttribute(lambda x: FAKER.lexify(text='??????????'))
    enable_generation_of_api_credentials = False
    learner_portal_sidebar_content = 'Test message'


class UserFactory(factory.django.DjangoModelFactory):
    """
    User factory.

    Creates an instance of User with minimal boilerplate - uses this class' attributes as default
    parameters for User constructor.
    """

    class Meta:
        """
        Meta for UserFactory.
        """

        model = User

    email = factory.LazyAttribute(lambda x: FAKER.email())
    username = factory.LazyAttribute(lambda x: FAKER.user_name() + str(randint(1, 10000)))
    first_name = factory.LazyAttribute(lambda x: FAKER.first_name())
    last_name = factory.LazyAttribute(lambda x: FAKER.last_name())
    is_staff = False
    is_active = False
    date_joined = factory.LazyAttribute(lambda x: FAKER.date_time_this_year(tzinfo=timezone.utc))


class EnterpriseCustomerUserFactory(factory.django.DjangoModelFactory):
    """
    EnterpriseCustomerUser factory.

    Creates an instance of EnterpriseCustomerUser with minimal boilerplate - uses this class' attributes as default
    parameters for EnterpriseCustomerUser constructor.
    """

    class Meta:
        """
        Meta for EnterpriseCustomerFactory.
        """

        model = EnterpriseCustomerUser
        django_get_or_create = ('enterprise_customer', 'user_id',)

    enterprise_customer = factory.SubFactory(EnterpriseCustomerFactory)
    user_id = factory.LazyAttribute(lambda x: UserFactory.create().id)
    active = True
    linked = True
    is_relinkable = True
    invite_key = None


class EnterpriseCustomerIdentityProviderFactory(factory.django.DjangoModelFactory):
    """
    Factory class for EnterpriseCustomerIdentityProvider model.
    """

    class Meta:
        """
        Meta for ``EnterpriseCustomerIdentityProviderFactory``.
        """

        model = EnterpriseCustomerIdentityProvider
        django_get_or_create = ("provider_id",)

    enterprise_customer = factory.SubFactory(EnterpriseCustomerFactory)
    provider_id = factory.LazyAttribute(lambda x: FAKER.slug())
    default_provider = False


class EnterpriseCourseEnrollmentFactory(factory.django.DjangoModelFactory):
    """
    EnterpriseCourseEnrollment factory.

    Creates an instance of EnterpriseCourseEnrollment with minimal boilerplate.
    """

    class Meta:
        """
        Meta for EnterpriseCourseEnrollmentFactory.
        """

        model = EnterpriseCourseEnrollment

    course_id = factory.LazyAttribute(lambda x: FAKER.slug())
    saved_for_later = False
    enterprise_customer_user = factory.SubFactory(EnterpriseCustomerUserFactory)


class LearnerCreditEnterpriseCourseEnrollmentFactory(factory.django.DjangoModelFactory):
    """
    LearnerCreditEnterpriseCourseEnrollment factory.
    """

    class Meta:
        """
        Meta for LearnerCreditEnterpriseCourseEnrollment.
        """

        model = LearnerCreditEnterpriseCourseEnrollment

    transaction_id = factory.LazyAttribute(lambda x: FAKER.uuid4())
    enterprise_course_enrollment = factory.SubFactory(EnterpriseCourseEnrollmentFactory)
    is_revoked = False
    fulfillment_type = FulfillmentTypes.LEARNER_CREDIT


class EnterpriseCatalogQueryFactory(factory.django.DjangoModelFactory):
    """
    EnterpriseCatalogQuery factory.

    Creates an instance of EnterpriseCatalogQuery with minimal boilerplate.
    """

    class Meta:
        """
        Meta for EnterpriseCatalogQuery.
        """

        model = EnterpriseCatalogQuery

    title = factory.Faker('sentence', nb_words=4)
    uuid = factory.LazyAttribute(lambda x: UUID(FAKER.uuid4()))


class EnterpriseCustomerCatalogFactory(factory.django.DjangoModelFactory):
    """
    EnterpriseCustomerCatalog factory.

    Creates an instance of EnterpriseCustomerCatalog with minimal boilerplate.
    """

    class Meta:
        """
        Meta for EnterpriseCustomerCatalog.
        """

        model = EnterpriseCustomerCatalog

    title = factory.Faker('sentence', nb_words=4)
    uuid = factory.LazyAttribute(lambda x: UUID(FAKER.uuid4()))
    enterprise_customer = factory.SubFactory(EnterpriseCustomerFactory)
    enterprise_catalog_query = factory.SubFactory(EnterpriseCatalogQueryFactory)


class DataSharingConsentFactory(factory.django.DjangoModelFactory):
    """
    ``DataSharingConsent`` factory.

    Creates an instance of ``DataSharingConsent`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``DataSharingConsentFactory``.
        """

        model = DataSharingConsent

    enterprise_customer = factory.SubFactory(EnterpriseCustomerFactory)
    username = factory.LazyAttribute(lambda x: FAKER.user_name())
    course_id = factory.LazyAttribute(lambda x: FAKER.slug())
    granted = True


class LearnerDataTransmissionAuditFactory(factory.django.DjangoModelFactory):
    """
    ``LearnerDataTransmissionAudit`` factory.

    Creates an instance of LearnerDataTransmissionAudit with minimal boilerplate
    """
    class Meta:
        """
        Meta for ``LearnerDataTransmissionAuditFactory``.
        """
        model = LearnerDataTransmissionAudit

    enterprise_customer_uuid = factory.LazyAttribute(lambda x: FAKER.uuid4())
    content_title = factory.LazyAttribute(lambda x: FAKER.word())
    status = factory.LazyAttribute(lambda x: str(FAKER.random_int(min=1)))
    plugin_configuration_id = factory.LazyAttribute(lambda x: FAKER.pyint())
    enterprise_course_enrollment_id = factory.LazyAttribute(lambda x: FAKER.pyint())
    course_id = factory.LazyAttribute(lambda x: FAKER.slug())
    completed_timestamp = factory.LazyAttribute(lambda x: FAKER.date_time_this_year(tzinfo=timezone.utc))


class GenericLearnerDataTransmissionAuditFactory(LearnerDataTransmissionAuditFactory):
    """
    ``GenericLearnerDataTransmissionAudit`` factory.

    Creates an instance of ``GenericLearnerDataTransmissionAudit`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``GenericLearnerDataTransmissionAuditFactory``.
        """

        model = GenericLearnerDataTransmissionAudit


class GenericEnterpriseCustomerPluginConfigurationFactory(factory.django.DjangoModelFactory):
    """
    ``GenericEnterpriseCustomerPluginConfiguration`` factory.

    Creates an instance of ``GenericEnterpriseCustomerPluginConfiguration`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``GenericEnterpriseCustomerPluginConfigurationFactgory``.
        """

        model = GenericEnterpriseCustomerPluginConfiguration

    enterprise_customer = factory.SubFactory(EnterpriseCustomerFactory)
    active = True
    dry_run_mode_enabled = False
    idp_id = ''


class SAPSuccessFactorsGlobalConfigurationFactory(factory.django.DjangoModelFactory):
    """
    ``SAPSuccessFactorsGlobalConfiguration`` factory.

    Creates an instance of ``SAPSuccessFactorsGlobalConfiguration`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``SAPSuccessFactorsGlobalConfigurationFactory``.
        """

        model = SAPSuccessFactorsGlobalConfiguration

    completion_status_api_path = factory.LazyAttribute(lambda x: FAKER.file_path())
    course_api_path = factory.LazyAttribute(lambda x: FAKER.file_path())
    oauth_api_path = factory.LazyAttribute(lambda x: FAKER.file_path())
    provider_id = 'SAP'


class SAPSuccessFactorsEnterpriseCustomerConfigurationFactory(GenericEnterpriseCustomerPluginConfigurationFactory):
    """
    ``SAPSuccessFactorsEnterpriseCustomerConfiguration`` factory.

    Creates an instance of ``SAPSuccessFactorsEnterpriseCustomerConfiguration`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``SAPSuccessFactorsEnterpriseCustomerConfigurationFactory``.
        """

        model = SAPSuccessFactorsEnterpriseCustomerConfiguration

    sapsf_base_url = factory.LazyAttribute(lambda x: FAKER.url())
    sapsf_company_id = factory.LazyAttribute(lambda x: FAKER.company())
    sapsf_user_id = factory.LazyAttribute(lambda x: FAKER.pyint())
    user_type = SAPSuccessFactorsEnterpriseCustomerConfiguration.USER_TYPE_USER


class SapSuccessFactorsLearnerDataTransmissionAuditFactory(LearnerDataTransmissionAuditFactory):
    """
    ``SapSuccessFactorsLearnerDataTransmissionAudit`` factory.

    Creates an instance of ``SapSuccessFactorsLearnerDataTransmissionAudit`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``SapSuccessFactorsLearnerDataTransmissionAuditFactory``.
        """

        model = SapSuccessFactorsLearnerDataTransmissionAudit

    sapsf_user_id = factory.LazyAttribute(lambda x: FAKER.pyint())
    enterprise_course_enrollment_id = factory.LazyAttribute(lambda x: FAKER.random_int(min=1))
    course_id = factory.LazyAttribute(lambda x: FAKER.slug())
    user_email = factory.LazyAttribute(lambda x: FAKER.email())
    instructor_name = factory.LazyAttribute(lambda x: FAKER.name())
    grade = factory.LazyAttribute(lambda x: FAKER.bothify('?', letters='ABCDF') + FAKER.bothify('?', letters='+-'))
    status = factory.LazyAttribute(lambda x: FAKER.word())
    course_completed = True
    sap_completed_timestamp = factory.LazyAttribute(lambda x: FAKER.random_int(min=1))


class Degreed2EnterpriseCustomerConfigurationFactory(factory.django.DjangoModelFactory):
    """
    ``Degreed2EnterpriseCustomerConfiguration`` factory.

    Creates an instance of ``Degreed2EnterpriseCustomerConfiguration`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``Degreed2EnterpriseCustomerConfigurationFactory``.
        """

        model = Degreed2EnterpriseCustomerConfiguration

    enterprise_customer = factory.SubFactory(EnterpriseCustomerFactory)
    active = True
    degreed_base_url = factory.LazyAttribute(lambda x: FAKER.url())
    degreed_token_fetch_base_url = factory.LazyAttribute(lambda x: FAKER.url())
    decrypted_client_id = factory.LazyAttribute(lambda x: FAKER.uuid4())
    decrypted_client_secret = factory.LazyAttribute(lambda x: FAKER.uuid4())


class CornerstoneLearnerDataTransmissionAuditFactory(LearnerDataTransmissionAuditFactory):
    """
    ``CornerstoneLearnerDataTransmissionAudit`` factory.

    Creates an instance of ``CornerstoneLearnerDataTransmissionAudit`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``CornerstoneLearnerDataTransmissionAuditFactory``.
        """

        model = CornerstoneLearnerDataTransmissionAudit
        django_get_or_create = ('user_id', 'course_id', )

    user_id = factory.LazyAttribute(lambda x: FAKER.pyint())
    course_id = factory.LazyAttribute(lambda x: FAKER.slug())
    user_guid = factory.LazyAttribute(lambda x: FAKER.slug())
    session_token = factory.LazyAttribute(lambda x: FAKER.slug())
    callback_url = factory.LazyAttribute(lambda x: FAKER.slug())
    subdomain = factory.LazyAttribute(lambda x: FAKER.slug())


class CornerstoneEnterpriseCustomerConfigurationFactory(factory.django.DjangoModelFactory):
    """
    ``CornerstoneEnterpriseCustomerConfiguration`` factory.

    Creates an instance of ``CornerstoneEnterpriseCustomerConfiguration`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``CornerstoneEnterpriseCustomerConfiguration``.
        """

        model = CornerstoneEnterpriseCustomerConfiguration

    enterprise_customer = factory.SubFactory(EnterpriseCustomerFactory)
    active = True
    cornerstone_base_url = factory.LazyAttribute(lambda x: FAKER.url())


class CornerstoneGlobalConfigurationFactory(factory.django.DjangoModelFactory):
    """
    ``CornerstoneGlobalConfiguration`` factory.

    Creates an instance of ``CornerstoneGlobalConfiguration`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``CornerstoneGlobalConfiguration``.
        """

        model = CornerstoneGlobalConfiguration

    completion_status_api_path = '/progress'
    key = factory.LazyAttribute(lambda x: FAKER.slug())
    secret = factory.LazyAttribute(lambda x: FAKER.uuid4())
    oauth_api_path = factory.LazyAttribute(lambda x: FAKER.file_path())
    subject_mapping = {
        "Technology": ["Computer Science"],
        "Business Skills": ["Communication"],
        "Creative": ["Music", "Design"]
    }
    languages = {"Languages": ["es-ES", "en-US", "ja-JP", "zh-CN"]}


class XAPILRSConfigurationFactory(factory.django.DjangoModelFactory):
    """
    ``XAPILRSConfiguration`` factory.

    Creates an instance of ``XAPILRSConfiguration`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``XAPILRSConfiguration``.
        """

        model = XAPILRSConfiguration

    enterprise_customer = factory.SubFactory(EnterpriseCustomerFactory)
    version = '1.0.1'
    endpoint = factory.LazyAttribute(lambda x: FAKER.url())
    key = factory.LazyAttribute(lambda x: FAKER.slug())
    secret = factory.LazyAttribute(lambda x: FAKER.uuid4())
    active = True


class XAPILearnerDataTransmissionAuditFactory(factory.django.DjangoModelFactory):
    """
    ``XAPILearnerDataTransmissionAudit`` factory.

    Creates an instance of ``XAPILearnerDataTransmissionAudit`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``XAPILearnerDataTransmissionAuditFactory``.
        """

        model = XAPILearnerDataTransmissionAudit

    user_id = factory.LazyAttribute(lambda x: FAKER.pyint())
    course_id = factory.LazyAttribute(lambda x: FAKER.slug())


class BlackboardGlobalConfigurationFactory(factory.django.DjangoModelFactory):
    """
    ``BlackboardGlobalConfiguration`` factory.

    Creates an instance of ``BlackboardGlobalConfiguration`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``BlackboardGlobalConfiguration``.
        """

        model = BlackboardGlobalConfiguration

    app_key = factory.LazyAttribute(lambda x: FAKER.random_int(min=1))
    app_secret = factory.LazyAttribute(lambda x: FAKER.uuid4())


class BlackboardEnterpriseCustomerConfigurationFactory(factory.django.DjangoModelFactory):
    """
    ``BlackboardEnterpriseCustomerConfiguration`` factory.

    Creates an instance of ``BlackboardEnterpriseCustomerConfiguration`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``BlackboardEnterpriseCustomerConfiguration``.
        """

        model = BlackboardEnterpriseCustomerConfiguration

    enterprise_customer = factory.SubFactory(EnterpriseCustomerFactory)
    active = True
    blackboard_base_url = factory.LazyAttribute(lambda x: FAKER.url())
    decrypted_client_id = factory.LazyAttribute(lambda x: FAKER.random_int(min=1))
    decrypted_client_secret = factory.LazyAttribute(lambda x: FAKER.uuid4())
    refresh_token = factory.LazyAttribute(lambda x: FAKER.uuid4())


class CanvasEnterpriseCustomerConfigurationFactory(factory.django.DjangoModelFactory):
    """
    ``CanvasEnterpriseCustomerConfiguration`` factory.

    Creates an instance of ``CanvasEnterpriseCustomerConfiguration`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``CanvasEnterpriseCustomerConfiguration``.
        """

        model = CanvasEnterpriseCustomerConfiguration

    enterprise_customer = factory.SubFactory(EnterpriseCustomerFactory)
    active = True
    canvas_account_id = 2
    canvas_base_url = factory.LazyAttribute(lambda x: FAKER.url())


class MoodleEnterpriseCustomerConfigurationFactory(factory.django.DjangoModelFactory):
    """
    ``MoodleEnterpriseCustomerConfiguration`` factory.

    Creates an instance of ``MoodleEnterpriseCustomerConfiguration`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``MoodleGlobalConfigurationFactory``.
        """

        model = MoodleEnterpriseCustomerConfiguration

    active = True
    enterprise_customer = factory.SubFactory(EnterpriseCustomerFactory)
    moodle_base_url = factory.LazyAttribute(lambda x: FAKER.url())
    service_short_name = factory.LazyAttribute(lambda x: FAKER.slug())
    decrypted_token = factory.LazyAttribute(lambda x: FAKER.slug())


class ContentMetadataItemTransmissionFactory(factory.django.DjangoModelFactory):
    """
    ``ContentMetadataItemTransmission`` factory.

    Create an instance of ``ContentMetadataItemTransmission`` with minimal boilerplate.
    """

    class Meta:
        """
        Meta for ``ContentMetadataItemTransmission``.
        """
        model = ContentMetadataItemTransmission

    enterprise_customer = factory.SubFactory(EnterpriseCustomerFactory)
    integrated_channel_code = 'GENERIC'
    plugin_configuration_id = factory.LazyAttribute(lambda x: FAKER.random_int(min=1))
    content_id = factory.LazyAttribute(lambda x: FAKER.slug())
    content_title = 'edX Demonstration Course'
    content_last_changed = localized_utcnow()
    api_response_status_code = None
    enterprise_customer_catalog_uuid = factory.LazyAttribute(lambda x: FAKER.uuid4())
    channel_metadata = {
        'title': 'edX Demonstration Course',
        'key': 'edX+DemoX',
        'content_type': 'course',
        'start': '2030-01-01T00:00:00Z',
        'end': '2030-03-01T00:00:00Z',
        'enrollment_url': 'https://www.foobar.com',
        'is_active': True,
        'estimated_hours': '666',
        'organizations': ['ayylmao'],
        'languages': 'Klingon',
        'subjects': 'ayylmaooo',
        'image_url': 'https://www,foobar.com'
    }


class OrphanedContentTransmissionsFactory(factory.django.DjangoModelFactory):
    """
    ``OrphanedContentTransmissions`` factory.
    """

    class Meta:
        """
        Meta for ``OrphanedContentTransmissions``.
        """

        model = OrphanedContentTransmissions

    integrated_channel_code = 'GENERIC'
    content_id = factory.LazyAttribute(lambda x: FAKER.slug())
    plugin_configuration_id = factory.LazyAttribute(lambda x: FAKER.random_int(min=1))
    resolved = False
    transmission = factory.Iterator(ContentMetadataItemTransmission.objects.all())
