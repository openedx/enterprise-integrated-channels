"""
Tests for the integrated channel models.
"""
import datetime
import unittest
from unittest import mock

import pytz
from enterprise.utils import get_content_metadata_item_id, localized_utcnow
from pytest import mark

from channel_integrations.integrated_channel.models import (
    ApiResponseRecord,
    ContentMetadataItemTransmission,
    EnterpriseCustomerPluginConfiguration,
    IntegratedChannelAPIRequestLogs,
)
from channel_integrations.sap_success_factors.models import SAPAuthType
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
class TestTransmissionPreflightCheck(unittest.TestCase):
    """
    Tests that the worker entry points refuse to run against an incomplete configuration.
    """

    def setUp(self):
        self.config = factories.SAPSuccessFactorsEnterpriseCustomerConfigurationFactory(
            decrypted_key='a-key',
            decrypted_secret='a-secret',
        )
        self.user = factories.UserFactory()
        super().setUp()

    def test_transmit_content_metadata_runs_when_configuration_is_complete(self):
        """
        A complete configuration still reaches the exporter and transmitter.
        """
        with mock.patch.object(self.config, 'get_content_metadata_exporter') as exporter, \
                mock.patch.object(self.config, 'get_content_metadata_transmitter') as transmitter:
            self.config.transmit_content_metadata(self.user)

        exporter.assert_called_once_with(self.user)
        transmitter.assert_called_once()

    def test_transmit_content_metadata_aborts_when_credentials_are_missing(self):
        """
        Content metadata transmission stops before building a client that would call SAP unauthenticated.
        """
        self.config.decrypted_secret = ''

        with mock.patch.object(self.config, 'get_content_metadata_exporter') as exporter, \
                mock.patch.object(self.config, 'get_content_metadata_transmitter') as transmitter:
            self.config.transmit_content_metadata(self.user)

        exporter.assert_not_called()
        transmitter.assert_not_called()

    def test_transmit_learner_data_runs_when_configuration_is_complete(self):
        """
        A complete configuration still reaches the exporter and transmitter.
        """
        with mock.patch.object(self.config, 'get_learner_data_exporter') as exporter, \
                mock.patch.object(self.config, 'get_learner_data_transmitter') as transmitter:
            self.config.transmit_learner_data(self.user)

        exporter.assert_called_once_with(self.user)
        transmitter.assert_called_once()

    def test_transmit_learner_data_aborts_when_credentials_are_missing(self):
        """
        Learner data transmission stops before building a client that would call SAP unauthenticated.
        """
        self.config.decrypted_key = ''

        with mock.patch.object(self.config, 'get_learner_data_exporter') as exporter, \
                mock.patch.object(self.config, 'get_learner_data_transmitter') as transmitter:
            self.config.transmit_learner_data(self.user)

        exporter.assert_not_called()
        transmitter.assert_not_called()

    def test_preflight_abort_names_the_missing_fields(self):
        """
        The abort log tells an operator which fields to fill in, so the sync gap is diagnosable.
        """
        self.config.decrypted_key = ''
        self.config.decrypted_secret = ''

        with mock.patch('channel_integrations.sap_success_factors.models.LOGGER') as logger:
            with mock.patch.object(self.config, 'get_content_metadata_exporter'):
                self.config.transmit_content_metadata(self.user)

        logger.warning.assert_called_once()
        logged_message = logger.warning.call_args[0][0]
        assert 'transmit_content_metadata aborted' in logged_message
        assert 'key' in logged_message
        assert 'secret' in logged_message

    def test_preflight_ignores_problems_that_do_not_block_authentication(self):
        """
        A cosmetic problem must not stop a customer that is otherwise syncing correctly.

        ``is_valid`` also reports an over-long ``display_name``; gating on that would silently take a
        working integration offline.
        """
        self.config.display_name = 'a-display-name-well-over-twenty-characters'

        _, incorrect = self.config.is_valid
        assert 'display_name' in incorrect['incorrect']

        with mock.patch.object(self.config, 'get_content_metadata_exporter') as exporter, \
                mock.patch.object(self.config, 'get_content_metadata_transmitter'):
            self.config.transmit_content_metadata(self.user)

        exporter.assert_called_once_with(self.user)

    def test_preflight_aborts_on_an_unparseable_private_key(self):
        """
        A key that is present but cannot be parsed still cannot sign an assertion.

        ``is_valid`` reports it under 'incorrect' rather than 'missing' because the field is filled
        in, but the transmission would fail just as surely -- and failing here is the whole point of
        validating the key, so the gate must not wave it through.
        """
        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.config.decrypted_private_key = (
            '-----BEGIN PRIVATE KEY-----\nnot-real-key-material\n-----END PRIVATE KEY-----\n'
        )

        missing, incorrect = self.config.is_valid
        assert 'private_key' not in missing['missing']
        assert 'private_key' in incorrect['incorrect']

        with mock.patch.object(self.config, 'get_content_metadata_exporter') as exporter, \
                mock.patch.object(self.config, 'get_content_metadata_transmitter') as transmitter:
            self.config.transmit_content_metadata(self.user)

        exporter.assert_not_called()
        transmitter.assert_not_called()

    def test_preflight_aborts_on_a_malformed_base_url(self):
        """
        A base URL that is present but not a URL leaves the channel unreachable.

        Also reported under 'incorrect', and also genuinely blocking.
        """
        self.config.sapsf_base_url = 'not a url at all'

        missing, incorrect = self.config.is_valid
        assert 'sapsf_base_url' not in missing['missing']
        assert 'sapsf_base_url' in incorrect['incorrect']

        with mock.patch.object(self.config, 'get_content_metadata_exporter') as exporter, \
                mock.patch.object(self.config, 'get_content_metadata_transmitter') as transmitter:
            self.config.transmit_content_metadata(self.user)

        exporter.assert_not_called()
        transmitter.assert_not_called()

    def test_preflight_abort_distinguishes_missing_from_invalid(self):
        """
        The log separates fields that were never filled in from ones that are filled in but unusable.

        "add a private key" and "the private key you added is truncated" need different actions from
        an operator, so the message must not flatten them into one wording.
        """
        self.config.auth_type = SAPAuthType.SELF_SIGNED_ASSERTION
        self.config.decrypted_private_key = 'not a key'
        self.config.saml_assertion_audience = ''

        with mock.patch('channel_integrations.sap_success_factors.models.LOGGER') as logger:
            with mock.patch.object(self.config, 'get_content_metadata_exporter'):
                self.config.transmit_content_metadata(self.user)

        logged_message = logger.warning.call_args[0][0]
        assert 'missing: saml_assertion_audience' in logged_message
        assert 'invalid: private_key' in logged_message

    def test_transmit_single_learner_data_runs_when_configuration_is_complete(self):
        """
        The per-learner completion path also reaches the exporter and transmitter when configured.
        """
        with mock.patch.object(self.config, 'get_learner_data_exporter') as exporter, \
                mock.patch.object(self.config, 'get_learner_data_transmitter') as transmitter:
            self.config.transmit_single_learner_data()

        exporter.assert_called_once()
        transmitter.assert_called_once()

    def test_transmit_single_learner_data_aborts_when_credentials_are_missing(self):
        """
        A single learner's grade sync is still a call to SAP with the same credentials -- gate it too.
        """
        self.config.decrypted_key = ''

        with mock.patch.object(self.config, 'get_learner_data_exporter') as exporter, \
                mock.patch.object(self.config, 'get_learner_data_transmitter') as transmitter:
            self.config.transmit_single_learner_data()

        exporter.assert_not_called()
        transmitter.assert_not_called()

    def test_transmit_subsection_learner_data_runs_when_configuration_is_complete(self):
        """
        The assessment-level sync path also reaches the exporter and transmitter when configured.
        """
        with mock.patch.object(self.config, 'get_learner_data_exporter') as exporter, \
                mock.patch.object(self.config, 'get_learner_data_transmitter') as transmitter:
            self.config.transmit_subsection_learner_data(self.user)

        exporter.assert_called_once_with(self.user)
        transmitter.assert_called_once()

    def test_transmit_subsection_learner_data_aborts_when_credentials_are_missing(self):
        """
        Assessment-level sync uses the same credentials as everything else -- gate it too.
        """
        self.config.decrypted_key = ''

        with mock.patch.object(self.config, 'get_learner_data_exporter') as exporter, \
                mock.patch.object(self.config, 'get_learner_data_transmitter') as transmitter:
            self.config.transmit_subsection_learner_data(self.user)

        exporter.assert_not_called()
        transmitter.assert_not_called()

    def test_transmit_single_subsection_learner_data_runs_when_configuration_is_complete(self):
        """
        The per-learner assessment-grade path also reaches the exporter and transmitter when configured.
        """
        with mock.patch.object(self.config, 'get_learner_data_exporter') as exporter, \
                mock.patch.object(self.config, 'get_learner_data_transmitter') as transmitter:
            self.config.transmit_single_subsection_learner_data()

        exporter.assert_called_once()
        transmitter.assert_called_once()

    def test_transmit_single_subsection_learner_data_aborts_when_credentials_are_missing(self):
        """
        A single learner's assessment grade sync is still a call to SAP -- gate it too.
        """
        self.config.decrypted_key = ''

        with mock.patch.object(self.config, 'get_learner_data_exporter') as exporter, \
                mock.patch.object(self.config, 'get_learner_data_transmitter') as transmitter:
            self.config.transmit_single_subsection_learner_data()

        exporter.assert_not_called()
        transmitter.assert_not_called()

    def test_cleanup_duplicate_assignment_records_runs_when_configuration_is_complete(self):
        """
        Deduplication also reaches the exporter and transmitter when the configuration is complete.
        """
        with mock.patch.object(self.config, 'get_learner_data_exporter') as exporter, \
                mock.patch.object(self.config, 'get_learner_data_transmitter') as transmitter:
            self.config.cleanup_duplicate_assignment_records(self.user)

        exporter.assert_called_once_with(self.user)
        transmitter.assert_called_once()

    def test_cleanup_duplicate_assignment_records_aborts_when_credentials_are_missing(self):
        """
        Deduplication calls the channel's API too, so it must not run unauthenticated either.
        """
        self.config.decrypted_key = ''

        with mock.patch.object(self.config, 'get_learner_data_exporter') as exporter, \
                mock.patch.object(self.config, 'get_learner_data_transmitter') as transmitter:
            self.config.cleanup_duplicate_assignment_records(self.user)

        exporter.assert_not_called()
        transmitter.assert_not_called()

    def test_aborted_content_metadata_still_updates_sync_timestamps(self):
        """
        A blocked content sync still moves last_sync_attempted_at/last_content_sync_errored_at, so an
        operator sees a broken configuration as erroring right now, not as a stale timestamp from
        whenever it last actually ran.
        """
        self.config.decrypted_secret = ''
        assert self.config.last_sync_attempted_at is None
        assert self.config.last_content_sync_errored_at is None

        before = localized_utcnow()
        with mock.patch.object(self.config, 'get_content_metadata_exporter'):
            self.config.transmit_content_metadata(self.user)

        self.config.refresh_from_db()
        assert self.config.last_sync_attempted_at >= before
        assert self.config.last_content_sync_errored_at >= before
        assert self.config.last_learner_sync_errored_at is None

    def test_aborted_learner_data_still_updates_sync_timestamps(self):
        """
        Same guarantee on the learner-data path, using its own errored-at field.
        """
        self.config.decrypted_key = ''
        before = localized_utcnow()
        with mock.patch.object(self.config, 'get_learner_data_exporter'):
            self.config.transmit_learner_data(self.user)

        self.config.refresh_from_db()
        assert self.config.last_sync_attempted_at >= before
        assert self.config.last_learner_sync_errored_at >= before
        assert self.config.last_content_sync_errored_at is None

    def test_successful_transmission_does_not_record_an_error_timestamp(self):
        """
        The abort path is the only one that marks an error -- a normal run must not trip it.
        """
        with mock.patch.object(self.config, 'get_content_metadata_exporter'), \
                mock.patch.object(self.config, 'get_content_metadata_transmitter'):
            self.config.transmit_content_metadata(self.user)

        self.config.refresh_from_db()
        assert self.config.last_sync_errored_at is None
        assert self.config.last_content_sync_errored_at is None

    def test_cleanup_duplicate_assignment_records_abort_does_not_touch_sync_timestamps(self):
        """
        Deduplication is not a sync cycle in its own right, so a blocked run here should not move
        last_sync_attempted_at and make a broken configuration look like it just synced.
        """
        self.config.decrypted_key = ''

        with mock.patch.object(self.config, 'get_learner_data_exporter'):
            self.config.cleanup_duplicate_assignment_records(self.user)

        self.config.refresh_from_db()
        assert self.config.last_sync_attempted_at is None

    def test_unlink_inactive_learners_aborts_when_credentials_are_missing(self):
        """
        Unlinking queries SAP for inactive learners, so it is gated like the transmission entry points,
        without moving the sync timestamps since it is not a sync cycle.
        """
        self.config.decrypted_secret = ''

        with mock.patch.object(self.config, 'get_learner_manger') as learner_manager:
            self.config.unlink_inactive_learners()

        learner_manager.assert_not_called()
        self.config.refresh_from_db()
        assert self.config.last_sync_attempted_at is None

    def test_unlink_inactive_learners_runs_when_configuration_is_complete(self):
        """
        A complete configuration still unlinks inactive learners.
        """
        with mock.patch.object(self.config, 'get_learner_manger') as learner_manager:
            self.config.unlink_inactive_learners()

        learner_manager.return_value.unlink_learners.assert_called_once_with()

    def test_gate_runs_ahead_of_disabled_learner_transmissions(self):
        """
        Pins a second-order effect of gating at the entry point rather than in the transmitter.

        ``disable_learner_data_transmissions`` is honoured inside the learner-data transmitters, so
        it is checked after this gate. A customer who has switched learner data off and also has an
        incomplete configuration therefore records a learner-sync error, where before the run was
        skipped in silence. Accepted: the configuration is genuinely broken and the content-metadata
        path would report it anyway. Pinned so that it stays a decision rather than a surprise.
        """
        self.config.disable_learner_data_transmissions = True
        self.config.decrypted_key = ''
        self.config.save()

        with mock.patch.object(self.config, 'get_learner_data_exporter') as exporter:
            self.config.transmit_learner_data(self.user)

        exporter.assert_not_called()
        self.config.refresh_from_db()
        assert self.config.last_learner_sync_errored_at is not None

    def test_sap_overrides_the_hook(self):
        """
        SAP is the one channel this ticket implements the hook for.
        """
        assert type(self.config).is_ready_to_transmit is not EnterpriseCustomerPluginConfiguration.is_ready_to_transmit


@mark.django_db
class TestTransmissionPreflightHookDefault(unittest.TestCase):
    """
    Tests that channels which have not overridden the hook are left on their existing behaviour.
    """

    def setUp(self):
        self.config = factories.Degreed2EnterpriseCustomerConfigurationFactory()
        self.user = factories.UserFactory()
        super().setUp()

    def test_hook_is_a_pass_through_by_default(self):
        """
        The base implementation lets everything through, so adding the hook is inert on its own.
        """
        assert type(self.config).is_ready_to_transmit is EnterpriseCustomerPluginConfiguration.is_ready_to_transmit
        assert self.config.is_ready_to_transmit('any_task') is True

    def test_incomplete_configuration_still_transmits_without_an_override(self):
        """
        A channel that has not overridden the hook keeps its behaviour, incomplete config and all.

        Degreed2 reports a blank client id as missing, so this configuration would be blocked if the
        base class gated on ``is_valid`` itself. Implementing the hook is per-channel and deliberate,
        reviewed against what that channel's ``is_valid`` actually requires.
        """
        self.config.decrypted_client_id = ''
        missing, _ = self.config.is_valid
        assert 'decrypted_client_id' in missing['missing']

        with mock.patch.object(self.config, 'get_content_metadata_exporter') as exporter, \
                mock.patch.object(self.config, 'get_content_metadata_transmitter') as transmitter:
            self.config.transmit_content_metadata(self.user)

        exporter.assert_called_once_with(self.user)
        transmitter.assert_called_once()
