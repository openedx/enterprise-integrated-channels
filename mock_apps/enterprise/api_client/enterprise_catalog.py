"""
Mock Client for communicating with the Enterprise API.
"""

from logging import getLogger
from urllib.parse import urljoin

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
