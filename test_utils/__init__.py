""" This module contains utility functions for testing. """

import uuid

FAKE_UUIDS = [str(uuid.uuid4()) for i in range(5)]

def update_search_with_enterprise_context(search_result, add_utm_info): # pylint: disable=unused-argument
    return []
