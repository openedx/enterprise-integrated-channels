from logging import getLogger

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from enterprise import models
from enterprise.utils import NotConnectedToOpenEdX
from enterprise.api_client.enterprise_catalog import EnterpriseCatalogApiClient
from channel_integrations.blackboard.models import BlackboardEnterpriseCustomerConfiguration
from channel_integrations.canvas.models import CanvasEnterpriseCustomerConfiguration
from channel_integrations.cornerstone.models import CornerstoneEnterpriseCustomerConfiguration
from channel_integrations.degreed2.models import Degreed2EnterpriseCustomerConfiguration
from channel_integrations.integrated_channel.tasks import mark_orphaned_content_metadata_audit
from channel_integrations.moodle.models import MoodleEnterpriseCustomerConfiguration
from channel_integrations.sap_success_factors.models import SAPSuccessFactorsEnterpriseCustomerConfiguration


logger = getLogger(__name__)

INTEGRATED_CHANNELS = [
    BlackboardEnterpriseCustomerConfiguration,
    CanvasEnterpriseCustomerConfiguration,
    CornerstoneEnterpriseCustomerConfiguration,
    Degreed2EnterpriseCustomerConfiguration,
    MoodleEnterpriseCustomerConfiguration,
    SAPSuccessFactorsEnterpriseCustomerConfiguration,
]

@receiver(post_save, sender=models.EnterpriseCustomerCatalog)
def update_enterprise_catalog_data(sender, instance, **kwargs):     # pylint: disable=unused-argument
    """
    Send data changes to Enterprise Catalogs to the Enterprise Catalog Service.

    Additionally sends a request to update the catalog's metadata from discovery, and index any relevant content for
    Algolia.
    """
    catalog_uuid = instance.uuid
    catalog_query_uuid = str(instance.enterprise_catalog_query.uuid) if instance.enterprise_catalog_query else None
    query_title = getattr(instance.enterprise_catalog_query, 'title', None)
    include_exec_ed_2u_courses = getattr(instance.enterprise_catalog_query, 'include_exec_ed_2u_courses', False)
    try:
        catalog_client = EnterpriseCatalogApiClient()
        if kwargs['created']:
            response = catalog_client.get_enterprise_catalog(
                catalog_uuid=catalog_uuid,
                # Suppress 404 exception on create since we do not expect the catalog
                # to exist yet in enterprise-catalog
                should_raise_exception=False,
            )
        else:
            response = catalog_client.get_enterprise_catalog(catalog_uuid=catalog_uuid)
    except NotConnectedToOpenEdX as exc:
        logger.exception(
            'Unable to update Enterprise Catalog {}'.format(str(catalog_uuid)), exc_info=exc
        )
    else:
        if not response:
            # catalog with matching uuid does NOT exist in enterprise-catalog
            # service, so we should create a new catalog
            catalog_client.create_enterprise_catalog(
                str(catalog_uuid),
                str(instance.enterprise_customer.uuid),
                instance.enterprise_customer.name,
                instance.title,
                instance.content_filter,
                instance.enabled_course_modes,
                instance.publish_audit_enrollment_urls,
                catalog_query_uuid,
                query_title,
                include_exec_ed_2u_courses,
            )
        else:
            # catalog with matching uuid does exist in enterprise-catalog
            # service, so we should update the existing catalog
            update_fields = {
                'enterprise_customer': str(instance.enterprise_customer.uuid),
                'enterprise_customer_name': instance.enterprise_customer.name,
                'title': instance.title,
                'content_filter': instance.content_filter,
                'enabled_course_modes': instance.enabled_course_modes,
                'publish_audit_enrollment_urls': instance.publish_audit_enrollment_urls,
                'catalog_query_uuid': catalog_query_uuid,
                'query_title': query_title,
                'include_exec_ed_2u_courses': include_exec_ed_2u_courses,
            }
            catalog_client.update_enterprise_catalog(catalog_uuid, **update_fields)
        # Refresh catalog on all creates and updates
        catalog_client.refresh_catalogs([instance])


@receiver(post_delete, sender=models.EnterpriseCustomerCatalog)
def delete_enterprise_catalog_data(sender, instance, **kwargs):     # pylint: disable=unused-argument
    """
    Send deletions of Enterprise Catalogs to the Enterprise Catalog Service.
    """
    catalog_uuid = instance.uuid
    try:
        catalog_client = EnterpriseCatalogApiClient()
        catalog_client.delete_enterprise_catalog(catalog_uuid)
    except NotConnectedToOpenEdX as exc:
        logger.exception(
            'Unable to delete Enterprise Catalog {}'.format(str(catalog_uuid)),
            exc_info=exc
        )

    customer = instance.enterprise_customer
    for channel in INTEGRATED_CHANNELS:
        if channel.objects.filter(enterprise_customer=customer, active=True).exists():
            logger.info(
                f"Catalog {catalog_uuid} deletion is linked to an active integrated channels config, running the mark"
                f"orphan content audits task"
            )
            mark_orphaned_content_metadata_audit.delay()
            break
