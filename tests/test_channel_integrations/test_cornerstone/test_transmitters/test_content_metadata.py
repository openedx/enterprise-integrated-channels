"""
Tests for the Cornerstone content metadata transmitter.
"""

import unittest
from datetime import datetime
from unittest import mock

from pytest import mark

from channel_integrations.cornerstone.transmitters.content_metadata import CornerstoneContentMetadataTransmitter
from channel_integrations.integrated_channel.models import ContentMetadataItemTransmission
from test_utils import factories


@mark.django_db
class TestCornerstoneContentMetadataTransmitter(unittest.TestCase):
    """
    Tests for the class ``CornerstoneContentMetadataTransmitter``.
    """

    def setUp(self):
        super().setUp()
        enterprise_customer = factories.EnterpriseCustomerFactory(name='Starfleet Academy')
        self.enterprise_customer_catalog = factories.EnterpriseCustomerCatalogFactory(
            enterprise_customer=enterprise_customer
        )
        self.enterprise_config = factories.CornerstoneEnterpriseCustomerConfigurationFactory(
            enterprise_customer=enterprise_customer
        )

    # @mock.patch('channel_integrations.cornerstone.transmitter.content_metadata._log_info')
    def test_cornerstone_transmitter_transmit_method_noop(self):
        record = factories.ContentMetadataItemTransmissionFactory(
            enterprise_customer=self.enterprise_config.enterprise_customer,
            plugin_configuration_id=self.enterprise_config.id,
            integrated_channel_code=self.enterprise_config.channel_code(),
            remote_created_at=datetime.utcnow(),
            remote_updated_at=None,
        )
        transmitter = CornerstoneContentMetadataTransmitter(self.enterprise_config)
        transmitter._log_info = mock.MagicMock()  # pylint: disable=protected-access

        transmitter.transmit({record.content_id: record}, {}, {})
        transmitter._log_info.assert_called_with(  # pylint: disable=protected-access
            f'Cornerstone base transmission invoked for config: {self.enterprise_config.id}. Treating as a NOOP'
        )

    def test_transmit_content_metadata_updates_records(self):
        """
        Test that the Cornerstone content metadata transmitter transmit for web method generates and updates the
        appropriate content records as well as returns a transmit payload of both update and create content.
        """
        self.enterprise_config.transmission_chunk_size = 3
        self.enterprise_config.save()
        content_id_1 = 'content_id_1'
        content_id_2 = 'content_id_2'
        content_id_3 = 'content_id_3'
        past_transmission_to_update = factories.ContentMetadataItemTransmissionFactory(
            content_id=content_id_1,
            enterprise_customer=self.enterprise_config.enterprise_customer,
            plugin_configuration_id=self.enterprise_config.id,
            integrated_channel_code=self.enterprise_config.channel_code(),
            content_last_changed='2021-07-16T15:11:10.521611Z',
            enterprise_customer_catalog_uuid=self.enterprise_customer_catalog.uuid,
            channel_metadata={},
            remote_created_at=datetime.utcnow(),
            remote_updated_at=None,
        )
        past_transmission_to_delete = factories.ContentMetadataItemTransmissionFactory(
            content_id=content_id_2,
            enterprise_customer=self.enterprise_config.enterprise_customer,
            plugin_configuration_id=self.enterprise_config.id,
            integrated_channel_code=self.enterprise_config.channel_code(),
            content_last_changed='2021-07-16T15:11:10.521611Z',
            enterprise_customer_catalog_uuid=self.enterprise_customer_catalog.uuid,
            remote_created_at=datetime.utcnow(),
            remote_deleted_at=None,
        )
        new_transmission_to_create = factories.ContentMetadataItemTransmissionFactory(
            content_id=content_id_3,
            enterprise_customer=self.enterprise_config.enterprise_customer,
            plugin_configuration_id=self.enterprise_config.id,
            integrated_channel_code=self.enterprise_config.channel_code(),
            content_last_changed='2021-07-16T15:11:10.521611Z',
            enterprise_customer_catalog_uuid=self.enterprise_customer_catalog.uuid,
            remote_created_at=None,
        )

        new_channel_metadata = {
            'title': 'edX Demonstration Course',
            'key': content_id_1,
            'content_type': 'course',
            'start': '2030-01-01T00:00:00Z',
            'end': '2030-03-01T00:00:00Z'
        }
        past_transmission_to_update.channel_metadata = new_channel_metadata

        transmitter = CornerstoneContentMetadataTransmitter(self.enterprise_config)

        create_payload = {
            content_id_3: new_transmission_to_create
        }
        update_payload = {
            content_id_1: past_transmission_to_update
        }
        delete_payload = {
            content_id_2: past_transmission_to_delete
        }
        transmitter.transmit_for_web(create_payload, update_payload, delete_payload)
        item_updated = ContentMetadataItemTransmission.objects.filter(
            enterprise_customer_catalog_uuid=self.enterprise_customer_catalog.uuid,
            content_id=content_id_1,
        ).first()
        assert item_updated.remote_updated_at
        assert item_updated.channel_metadata == new_channel_metadata
        item_deleted = ContentMetadataItemTransmission.objects.filter(
            enterprise_customer_catalog_uuid=self.enterprise_customer_catalog.uuid,
            content_id=content_id_2,
        ).first()
        assert item_deleted.remote_deleted_at
        item_created = ContentMetadataItemTransmission.objects.filter(
            enterprise_customer_catalog_uuid=self.enterprise_customer_catalog.uuid,
            content_id=content_id_3,
        ).first()
        assert item_created.remote_created_at
