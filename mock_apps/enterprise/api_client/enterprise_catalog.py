"""
Mock Client for communicating with the Enterprise API.
"""


class EnterpriseCatalogApiClient:
    """
    The API client to make calls to the Enterprise Catalog API.
    """

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

        return [], [], []

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
        return []
