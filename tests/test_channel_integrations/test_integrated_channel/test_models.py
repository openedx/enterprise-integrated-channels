"""
Tests for the integrated channel models.
"""
import datetime
import unittest
from unittest import mock

import ddt
import pytz
from pytest import mark

from enterprise.utils import get_content_metadata_item_id, localized_utcnow
from channel_integrations.integrated_channel.models import (
    ApiResponseRecord,
    ContentMetadataItemTransmission,
    IntegratedChannelAPIRequestLogs,
)
from test_utils import factories
from test_utils.fake_catalog_api import FAKE_COURSE_RUN, get_fake_catalog, get_fake_content_metadata
from test_utils.fake_enterprise_api import EnterpriseMockMixin


@mark.django_db
class TestContentMetadataItemTransmission(unittest.TestCase, EnterpriseMockMixin):
    """
    Tests for the ``ContentMetadataItemTransmission`` model.
    """

    def setUp(self):
        self.enterprise_customer = factories.EnterpriseCustomerFactory()
        with mock.patch('enterprise.signals.EnterpriseCatalogApiClient'):
            self.enterprise_customer_catalog = factories.EnterpriseCustomerCatalogFactory(
                enterprise_customer=self.enterprise_customer,
            )

        self.config = factories.GenericEnterpriseCustomerPluginConfigurationFactory(
            enterprise_customer=self.enterprise_customer_catalog.enterprise_customer,
        )

        # Mocks
        self.mock_enterprise_customer_catalogs(str(self.enterprise_customer_catalog.uuid))
        self.fake_catalog = get_fake_catalog()
        self.fake_catalog_modified_at = max(
            self.fake_catalog['content_last_modified'], self.fake_catalog['catalog_modified']
        )
        self.fake_catalogs_last_modified = {
            get_content_metadata_item_id(
                content_metadata
            ): self.fake_catalog_modified_at for content_metadata in get_fake_content_metadata()
        }
        super().setUp()

    def test_content_meta_data_string_representation(self):
        """
        Test the string representation of the model.
        """
        integrated_channel_code = 'test-channel-code'
        content_id = 'test-course'
        expected_string = '<Content item {content_id} for Customer {customer} with Channel {channel}>'.format(
            content_id=content_id,
            customer=self.enterprise_customer,
            channel=integrated_channel_code
        )
        transmission = ContentMetadataItemTransmission(
            enterprise_customer=self.enterprise_customer,
            integrated_channel_code=integrated_channel_code,
            content_id=content_id
        )
        assert expected_string == repr(transmission)

    def test_failed_delete_transmissions_getter(self):
        """
        Test that we properly find created but unsent transmission audit items
        """
        api_record = ApiResponseRecord(status_code=500, body='ERROR')
        api_record.save()
        deleted_transmission = ContentMetadataItemTransmission(
            enterprise_customer=self.config.enterprise_customer,
            plugin_configuration_id=self.config.id,
            integrated_channel_code=self.config.channel_code(),
            content_id=FAKE_COURSE_RUN['key'],
            channel_metadata={},
            content_last_changed=datetime.datetime.now() - datetime.timedelta(hours=1),
            enterprise_customer_catalog_uuid=self.config.enterprise_customer.enterprise_customer_catalogs.first().uuid,
            remote_created_at=datetime.datetime.utcnow(),
            remote_updated_at=None,
            remote_deleted_at=datetime.datetime.utcnow(),
            api_response_status_code=500,
            api_record=api_record,
        )
        deleted_transmission.save()
        found_item = ContentMetadataItemTransmission.incomplete_delete_transmissions(
            self.enterprise_customer,
            self.config.id,
            self.config.channel_code(),
            FAKE_COURSE_RUN['key'],
        ).first()
        assert found_item == deleted_transmission

    def test_failed_update_transmissions_getter(self):
        """
        Test that we properly find created but unsent transmission audit items
        """
        api_record = ApiResponseRecord(status_code=500, body='ERROR')
        api_record.save()
        updated_transmission = ContentMetadataItemTransmission(
            enterprise_customer=self.config.enterprise_customer,
            plugin_configuration_id=self.config.id,
            integrated_channel_code=self.config.channel_code(),
            content_id=FAKE_COURSE_RUN['key'],
            channel_metadata={},
            content_last_changed=datetime.datetime.now() - datetime.timedelta(hours=1),
            enterprise_customer_catalog_uuid=self.config.enterprise_customer.enterprise_customer_catalogs.first().uuid,
            remote_created_at=datetime.datetime.utcnow(),
            remote_updated_at=datetime.datetime.utcnow(),
            remote_deleted_at=None,
            api_response_status_code=500,
            api_record=api_record,
        )
        updated_transmission.save()
        found_item = ContentMetadataItemTransmission.incomplete_update_transmissions(
            self.enterprise_customer,
            self.config.id,
            self.config.channel_code(),
            FAKE_COURSE_RUN['key'],
        ).first()
        assert found_item == updated_transmission

    def test_incomplete_create_transmissions_getter(self):
        """
        Test that we properly find created but unsent transmission audit items
        """
        incomplete_transmission = ContentMetadataItemTransmission(
            enterprise_customer=self.config.enterprise_customer,
            plugin_configuration_id=self.config.id,
            integrated_channel_code=self.config.channel_code(),
            content_id=FAKE_COURSE_RUN['key'],
            channel_metadata={},
            content_last_changed=datetime.datetime.now() - datetime.timedelta(hours=1),
            enterprise_customer_catalog_uuid=self.config.enterprise_customer.enterprise_customer_catalogs.first().uuid,
            remote_created_at=None,
            remote_updated_at=None,
            remote_deleted_at=None,
        )
        incomplete_transmission.save()
        found_item = ContentMetadataItemTransmission.incomplete_create_transmissions(
            self.enterprise_customer,
            self.config.id,
            self.config.channel_code(),
            FAKE_COURSE_RUN['key'],
        ).first()
        assert found_item == incomplete_transmission

    def test_failed_incomplete_create_transmissions_getter(self):
        """
        Test that we properly find created and attempted but unsuccessful transmission audit items
        """
        api_record = ApiResponseRecord(status_code=500, body='ERROR')
        api_record.save()
        failed_transmission = ContentMetadataItemTransmission(
            enterprise_customer=self.config.enterprise_customer,
            plugin_configuration_id=self.config.id,
            integrated_channel_code=self.config.channel_code(),
            content_id=FAKE_COURSE_RUN['key'],
            channel_metadata={},
            content_last_changed=datetime.datetime.now() - datetime.timedelta(hours=1),
            enterprise_customer_catalog_uuid=self.config.enterprise_customer.enterprise_customer_catalogs.first().uuid,
            remote_created_at=datetime.datetime.utcnow(),
            remote_updated_at=None,
            remote_deleted_at=None,
            api_response_status_code=500,
            api_record=api_record,
        )
        failed_transmission.save()
        found_item = ContentMetadataItemTransmission.incomplete_create_transmissions(
            self.enterprise_customer,
            self.config.id,
            self.config.channel_code(),
            FAKE_COURSE_RUN['key'],
        ).first()
        assert found_item == failed_transmission


@mark.django_db
class TestEnterpriseCustomerPluginConfiguration(unittest.TestCase, EnterpriseMockMixin):
    """
    Tests for the ``EnterpriseCustomerPluginConfiguration`` model.
    """

    def setUp(self):
        self.enterprise_customer = factories.EnterpriseCustomerFactory()
        self.config = factories.GenericEnterpriseCustomerPluginConfigurationFactory(
            enterprise_customer=self.enterprise_customer,
        )
        super().setUp()

    def test_update_content_synced_at(self):
        """
        Test synced_at timestamps for content data.
        """
        first_timestamp = datetime.datetime.fromtimestamp(1400000000).replace(tzinfo=pytz.utc)
        self.config.update_content_synced_at(first_timestamp, True)
        assert self.config.last_sync_attempted_at == first_timestamp
        assert self.config.last_content_sync_attempted_at == first_timestamp
        assert self.config.last_learner_sync_attempted_at is None
        assert self.config.last_sync_errored_at is None
        assert self.config.last_content_sync_errored_at is None
        assert self.config.last_learner_sync_errored_at is None

        second_timestamp = datetime.datetime.fromtimestamp(1500000000).replace(tzinfo=pytz.utc)
        self.config.update_content_synced_at(second_timestamp, False)
        assert self.config.last_sync_attempted_at == second_timestamp
        assert self.config.last_content_sync_attempted_at == second_timestamp
        assert self.config.last_learner_sync_attempted_at is None
        assert self.config.last_sync_errored_at == second_timestamp
        assert self.config.last_content_sync_errored_at == second_timestamp
        assert self.config.last_learner_sync_errored_at is None

        # if passing a date older than what we've already recorded, no-op
        self.config.update_content_synced_at(first_timestamp, True)
        assert self.config.last_sync_attempted_at == second_timestamp
        assert self.config.last_content_sync_attempted_at == second_timestamp

    def test_update_learner_synced_at(self):
        """
        Test synced_at timestamps for learner data.
        """
        first_timestamp = datetime.datetime.fromtimestamp(1400000000).replace(tzinfo=pytz.utc)
        self.config.update_learner_synced_at(first_timestamp, True)
        assert self.config.last_sync_attempted_at == first_timestamp
        assert self.config.last_content_sync_attempted_at is None
        assert self.config.last_learner_sync_attempted_at == first_timestamp
        assert self.config.last_sync_errored_at is None
        assert self.config.last_content_sync_errored_at is None
        assert self.config.last_learner_sync_errored_at is None

        second_timestamp = datetime.datetime.fromtimestamp(1500000000).replace(tzinfo=pytz.utc)
        self.config.update_learner_synced_at(second_timestamp, False)
        assert self.config.last_sync_attempted_at == second_timestamp
        assert self.config.last_content_sync_attempted_at is None
        assert self.config.last_learner_sync_attempted_at == second_timestamp
        assert self.config.last_sync_errored_at == second_timestamp
        assert self.config.last_content_sync_errored_at is None
        assert self.config.last_learner_sync_errored_at == second_timestamp

        # if passing a date older than what we've already recorded, no-op
        self.config.update_learner_synced_at(first_timestamp, True)
        assert self.config.last_sync_attempted_at == second_timestamp
        assert self.config.last_learner_sync_attempted_at == second_timestamp

    def test_offset_naive_error(self):
        """
        Test ENT-6661 comparison bug of offset-naive and offset-aware datetimes
        """
        self.config.last_sync_attempted_at = datetime.datetime.fromtimestamp(1500000000).replace(tzinfo=pytz.utc)
        first_timestamp = localized_utcnow()
        self.config.update_content_synced_at(first_timestamp, True)
        assert self.config.last_sync_attempted_at == first_timestamp


@mark.django_db
class TestIntegratedChannelAPIRequestLogs(unittest.TestCase, EnterpriseMockMixin):
    """
    Tests for the ``IntegratedChannelAPIRequestLogs`` model.
    """

    def setUp(self):
        self.enterprise_customer = factories.EnterpriseCustomerFactory()
        with mock.patch('enterprise.api_client.enterprise_catalog.EnterpriseCatalogApiClient'):
            self.enterprise_customer_catalog = factories.EnterpriseCustomerCatalogFactory(
                enterprise_customer=self.enterprise_customer,
            )
        self.pk = 1
        self.enterprise_customer_configuration_id = 1
        self.endpoint = 'https://example.com/endpoint'
        self.payload = "{}"
        self.time_taken = 500
        self.response_body = "{}"
        self.status_code = 200
        super().setUp()

    def test_content_meta_data_string_representation(self):
        """
        Test the string representation of the model.
        """
        expected_string = (
            f'<IntegratedChannelAPIRequestLog {self.pk}'
            f' for enterprise customer {self.enterprise_customer} '
            f', enterprise_customer_configuration_id: {self.enterprise_customer_configuration_id}>'
            f', endpoint: {self.endpoint}'
            f', time_taken: {self.time_taken}'
            f", response_body: {self.response_body}"
            f", status_code: {self.status_code}"
        )

        request_log = IntegratedChannelAPIRequestLogs(
            id=1,
            enterprise_customer=self.enterprise_customer,
            enterprise_customer_configuration_id=self.enterprise_customer_configuration_id,
            endpoint=self.endpoint,
            payload=self.payload,
            time_taken=self.time_taken,
            response_body=self.response_body,
            status_code=self.status_code
        )
        assert expected_string == repr(request_log)


@mark.django_db
@ddt.ddt
class TestIsReadyToTransmitHook(unittest.TestCase):
    """
    Tests that the transmission entry points consult ``is_ready_to_transmit`` before doing any work.
    """

    def setUp(self):
        self.config = factories.Degreed2EnterpriseCustomerConfigurationFactory()
        self.user = factories.UserFactory()
        super().setUp()

    def test_default_hook_lets_an_incomplete_configuration_transmit(self):
        """
        A channel that does not override the hook keeps transmitting, whatever ``is_valid`` reports.
        """
        self.config.decrypted_client_id = ''
        missing, _ = self.config.is_valid
        assert 'decrypted_client_id' in missing['missing']
        assert self.config.is_ready_to_transmit('transmit_content_metadata') is True

        with mock.patch.object(self.config, 'get_content_metadata_exporter') as exporter, \
                mock.patch.object(self.config, 'get_content_metadata_transmitter') as transmitter:
            self.config.transmit_content_metadata(self.user)

        exporter.assert_called_once_with(self.user)
        transmitter.assert_called_once()

    @ddt.data(
        {
            'entry_point': 'transmit_content_metadata',
            'takes_user': True,
            'exporter_getter': 'get_content_metadata_exporter',
            'record_attempt': 'update_content_synced_at',
        },
        {
            'entry_point': 'transmit_learner_data',
            'takes_user': True,
            'exporter_getter': 'get_learner_data_exporter',
            'record_attempt': 'update_learner_synced_at',
        },
        {
            'entry_point': 'transmit_single_learner_data',
            'takes_user': False,
            'exporter_getter': 'get_learner_data_exporter',
            'record_attempt': 'update_learner_synced_at',
        },
        {
            'entry_point': 'transmit_subsection_learner_data',
            'takes_user': True,
            'exporter_getter': 'get_learner_data_exporter',
            'record_attempt': 'update_learner_synced_at',
        },
        {
            'entry_point': 'transmit_single_subsection_learner_data',
            'takes_user': False,
            'exporter_getter': 'get_learner_data_exporter',
            'record_attempt': 'update_learner_synced_at',
        },
        # Deduplication is not a sync cycle, so a blocked run has no sync timestamps to record.
        {
            'entry_point': 'cleanup_duplicate_assignment_records',
            'takes_user': True,
            'exporter_getter': 'get_learner_data_exporter',
            'record_attempt': None,
        },
    )
    @ddt.unpack
    def test_entry_point_is_gated_by_the_hook(self, entry_point, takes_user, exporter_getter, record_attempt):
        """
        An entry point exports when the hook allows it, and when the hook refuses, stops before exporting
        and records the blocked run itself (when the entry point is a sync cycle).
        """
        args = (self.user,) if takes_user else ()

        for ready in (True, False):
            with self.subTest(ready=ready), \
                    mock.patch.object(self.config, 'is_ready_to_transmit', return_value=ready) as hook, \
                    mock.patch.object(self.config, exporter_getter) as exporter, \
                    mock.patch.object(self.config, 'get_content_metadata_transmitter'), \
                    mock.patch.object(self.config, 'get_learner_data_transmitter'), \
                    mock.patch.object(self.config, 'update_content_synced_at') as update_content_synced_at, \
                    mock.patch.object(self.config, 'update_learner_synced_at') as update_learner_synced_at:
                getattr(self.config, entry_point)(*args)

                assert hook.call_args.args == (entry_point,)
                assert exporter.called is ready

                if record_attempt is None or ready:
                    update_content_synced_at.assert_not_called()
                    update_learner_synced_at.assert_not_called()
                else:
                    getattr(self.config, record_attempt).assert_called_once_with(mock.ANY, False)
