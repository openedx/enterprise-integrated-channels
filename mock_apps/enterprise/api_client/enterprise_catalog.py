"""
Mock Client for communicating with the Enterprise API.
"""


class EnterpriseCatalogApiClient:
    """
    The API client to make calls to the Enterprise Catalog API.
    """

    def get_catalog_diff(self, enterprise_customer_catalog, content_keys, should_raise_exception=True):
        return [], [], []

    def get_content_metadata(self, enterprise_customer, enterprise_catalogs=None, content_keys_filter=None):
        return []
    
    def get_customer_content_metadata_content_identifier(self, enterprise_uuid, content_id):
        return {}
