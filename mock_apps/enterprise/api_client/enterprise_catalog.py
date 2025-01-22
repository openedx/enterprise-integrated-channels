"""
Mock Client for communicating with the Enterprise API.
"""

import json
from collections import OrderedDict
from logging import getLogger
from urllib.parse import urljoin

from requests.exceptions import ConnectionError, RequestException, Timeout  # pylint: disable=redefined-builtin

from django.conf import settings
from enterprise import utils
from enterprise.api_client.client import UserAPIClient

LOGGER = getLogger(__name__)


class EnterpriseCatalogApiClient(UserAPIClient):
    """
    The API client to make calls to the Enterprise Catalog API.
    """

    API_BASE_URL = urljoin(f"{settings.ENTERPRISE_CATALOG_INTERNAL_ROOT_URL}/", "api/v1/")
    ENTERPRISE_CATALOG_ENDPOINT = 'enterprise-catalogs'
    GET_CONTENT_METADATA_ENDPOINT = ENTERPRISE_CATALOG_ENDPOINT + '/{}/get_content_metadata'
    REFRESH_CATALOG_ENDPOINT = ENTERPRISE_CATALOG_ENDPOINT + '/{}/refresh_metadata'
    CATALOG_DIFF_ENDPOINT = ENTERPRISE_CATALOG_ENDPOINT + '/{}/generate_diff'
    ENTERPRISE_CUSTOMER_ENDPOINT = 'enterprise-customer'
    CONTENT_METADATA_IDENTIFIER_ENDPOINT = ENTERPRISE_CUSTOMER_ENDPOINT + \
        "/{}/content-metadata/" + "{}"
    CATALOG_QUERIES_ENDPOINT = 'catalog-queries'
    GET_CONTENT_FILTER_HASH_ENDPOINT = CATALOG_QUERIES_ENDPOINT + '/get_content_filter_hash'
    GET_QUERY_BY_HASH_ENDPOINT = CATALOG_QUERIES_ENDPOINT + '/get_query_by_hash?hash={}'
    APPEND_SLASH = True
    GET_CONTENT_METADATA_PAGE_SIZE = getattr(settings, 'ENTERPRISE_CATALOG_GET_CONTENT_METADATA_PAGE_SIZE', 50)

    def __init__(self, user=None):
        user = user if user else utils.get_enterprise_worker_user()
        super().__init__(user)

    @UserAPIClient.refresh_token
    def get_catalog_diff(self, enterprise_customer_catalog, content_keys, should_raise_exception=True):
        """
        Gets the representational difference between a list of course keys and the current state of content under an
        enterprise catalog. This difference is returned as three buckets of data: `items_not_found`,
        `items_not_included` and `items_found`.

        Arguments:
            enterprise_customer_catalog (EnterpriseCustomerCatalog): The catalog object whose content is being diffed.
            content_keys (list): List of string content keys
            should_raise_exception (Bool): Optional param for whether or not api response exceptions should be raised.

        Returns:
            items_to_create (list): dictionaries of content_keys to create
            items_to_delete (list): dictionaries of content_keys to delete
            items_found (list): dictionaries of content_keys and date_updated datetimes of content to update
        """
        catalog_uuid = enterprise_customer_catalog.uuid
        api_url = self.get_api_url(self.CATALOG_DIFF_ENDPOINT.format(catalog_uuid))
        body = {'content_keys': content_keys}

        items_to_delete = []
        items_to_create = []
        items_found = []
        try:
            response = self.client.post(api_url, json=body)
            response.raise_for_status()
            results = response.json()
            items_to_delete = results.get('items_not_found')
            items_to_create = results.get('items_not_included')
            items_found = results.get('items_found')

        except (RequestException, ConnectionError, Timeout) as exc:
            LOGGER.exception(
                'Failed to get EnterpriseCustomer Catalog [%s] in enterprise-catalog due to: [%s]',
                catalog_uuid, str(exc)
            )
            if should_raise_exception:
                raise

        return items_to_create, items_to_delete, items_found

    @UserAPIClient.refresh_token
    def get_content_metadata(self, enterprise_customer, enterprise_catalogs=None, content_keys_filter=None):
        """
        Return all content metadata contained in the catalogs associated with the EnterpriseCustomer.

        Arguments:
            enterprise_customer (EnterpriseCustomer): The EnterpriseCustomer to return content metadata for.
            enterprise_catalogs (EnterpriseCustomerCatalog): Optional list of EnterpriseCustomerCatalog objects.
            content_keys_filter (List): List of content keys to filter by in the content metadata endpoint

        Returns:
            list: List of dicts containing content metadata.
        """
        content_metadata = OrderedDict()
        enterprise_customer_catalogs = enterprise_catalogs or enterprise_customer.enterprise_customer_catalogs.all()
        for enterprise_customer_catalog in enterprise_customer_catalogs:
            catalog_uuid = enterprise_customer_catalog.uuid
            api_url = self.get_api_url(self.GET_CONTENT_METADATA_ENDPOINT.format(catalog_uuid))
            # If content keys filter exists then chunk up the keys into reasonable request sizes
            if content_keys_filter:
                chunked_keys_filter = utils.batch(
                    content_keys_filter,
                    self.GET_CONTENT_METADATA_PAGE_SIZE
                )
                # A chunk can be larger than the page size so traverse pagination for each individual chunk
                for chunk in chunked_keys_filter:
                    query = {'page_size': self.GET_CONTENT_METADATA_PAGE_SIZE, 'content_keys': chunk}
                    content_metadata.update(self.traverse_get_content_metadata(api_url, query, catalog_uuid))
            # Traverse pagination for the get all content response without filters
            else:
                query = {'page_size': self.GET_CONTENT_METADATA_PAGE_SIZE}
                content_metadata.update(self.traverse_get_content_metadata(api_url, query, catalog_uuid))

        return list(content_metadata.values())
