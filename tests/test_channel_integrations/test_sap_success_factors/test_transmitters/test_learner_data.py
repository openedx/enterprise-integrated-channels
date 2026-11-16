"""
Tests for SAPSF learner data transmissions.
"""

import datetime
import unittest
from unittest import mock

import ddt
from pytest import mark
from waffle.testutils import override_switch

from channel_integrations.exceptions import ClientError
from channel_integrations.integrated_channel.channel_settings import ENABLE_FAILED_GRADE_TRANSMISSION_SWITCH
from channel_integrations.sap_success_factors.models import SapSuccessFactorsLearnerDataTransmissionAudit
from channel_integrations.sap_success_factors.transmitters import learner_data
from test_utils import factories


@ddt.ddt
@mark.django_db
class TestSapSuccessFactorsLearnerDataTransmitter(unittest.TestCase):
    """
    Test SapSuccessFactorsLearnerTransmitter.
    """

    def setUp(self):
        super().setUp()
        self.global_config = factories.SAPSuccessFactorsGlobalConfigurationFactory()
        self.enterprise_customer = factories.EnterpriseCustomerFactory()
        self.enterprise_customer_user = factories.EnterpriseCustomerUserFactory(
            enterprise_customer=self.enterprise_customer
        )
        self.enterprise_course_enrollment = factories.EnterpriseCourseEnrollmentFactory(
            id=5,
            enterprise_customer_user=self.enterprise_customer_user
        )
        self.enterprise_config = factories.SAPSuccessFactorsEnterpriseCustomerConfigurationFactory(
            enterprise_customer=self.enterprise_customer,
            decrypted_key="client_id",
            sapsf_base_url="http://test.successfactors.com/",
            sapsf_company_id="company_id",
            sapsf_user_id="user_id",
            decrypted_secret="client_secret"
        )
        self.payloads = [
            SapSuccessFactorsLearnerDataTransmissionAudit(
                enterprise_course_enrollment_id=self.enterprise_course_enrollment.id,
                sapsf_user_id='sap_user',
                course_id='course-v1:edX+DemoX+DemoCourse',
                course_completed=True,
                sap_completed_timestamp=1486855998,
                completed_timestamp=datetime.datetime.fromtimestamp(1486855998),
                instructor_name='Professor Professorson',
                grade='Passing even more',
                error_message='',
                status=200,
                enterprise_customer_uuid=self.enterprise_customer.uuid,
                plugin_configuration_id=self.enterprise_config.id,
                is_transmitted=True
            )
        ]
        self.exporter = lambda payloads=self.payloads: mock.MagicMock(
            export=mock.MagicMock(return_value=iter(payloads)),
            grade_failing='Fail',
        )

        # Mocks
        get_oauth_access_token_mock = mock.patch(
            'channel_integrations.sap_success_factors.client.SAPSuccessFactorsAPIClient.get_oauth_access_token'
        )
        self.get_oauth_access_token_mock = get_oauth_access_token_mock.start()
        self.get_oauth_access_token_mock.return_value = "token", datetime.datetime.utcnow()
        self.addCleanup(get_oauth_access_token_mock.stop)

        create_course_completion_mock = mock.patch(
            'channel_integrations.sap_success_factors.client.SAPSuccessFactorsAPIClient.create_course_completion'
        )
        self.create_course_completion_mock = create_course_completion_mock.start()
        self.addCleanup(create_course_completion_mock.stop)

    def test_transmit_already_sent(self):
        """
        If we already sent a payload (we can tell if we did if it exists), don't send again.
        """
        self.payloads[0].save()
        transmitter = learner_data.SapSuccessFactorsLearnerTransmitter(self.enterprise_config)
        transmitter.transmit(self.exporter())
        self.create_course_completion_mock.assert_not_called()

    def test_avoid_retransmit_on_grade_change(self):
        """
        SAPSF does not support retransmsmitting completion, so we don't do that
        if just a grade changed relative to what is already saved
        """

        self.payloads[0].save()

        # let's try to send a payload with everything same except the grade
        payload = self.payloads[0]
        payload.grade = 'a_bit_different_grade'

        transmitter = learner_data.SapSuccessFactorsLearnerTransmitter(self.enterprise_config)
        transmitter.transmit(self.exporter([payload]))
        self.create_course_completion_mock.assert_not_called()

    def test_transmit_success(self):
        """
        Learner data transmission is successful and the payload is saved with the appropriate data.
        """
        self.create_course_completion_mock.return_value = 200, '{"success":"true"}'
        payload = SapSuccessFactorsLearnerDataTransmissionAudit(
            enterprise_course_enrollment_id=self.enterprise_course_enrollment.id,
            sapsf_user_id='sap_user',
            course_id='course-v1:edX+DemoX+DemoCourse',
            course_completed=True,
            sap_completed_timestamp=1486755998,
            completed_timestamp=datetime.datetime.fromtimestamp(1486755998),
            instructor_name='Professor Professorson',
            grade='Pass',
            enterprise_customer_uuid=self.enterprise_customer.uuid,
            plugin_configuration_id=self.enterprise_config.id,
        )
        transmitter = learner_data.SapSuccessFactorsLearnerTransmitter(self.enterprise_config)
        transmitter.transmit(self.exporter([payload]))
        self.create_course_completion_mock.assert_called_with(payload.sapsf_user_id, payload.serialize())
        assert payload.status == '200'
        assert payload.error_message == ''
        assert payload.is_transmitted is True

    def test_transmit_failure(self):
        """
        Learner data transmission fails for some reason and the payload is saved with the appropriate data.
        """
        self.create_course_completion_mock.side_effect = ClientError('error occurred')
        payload = SapSuccessFactorsLearnerDataTransmissionAudit(
            enterprise_course_enrollment_id=self.enterprise_course_enrollment.id,
            sapsf_user_id='sap_user',
            course_id='course-v1:edX+DemoX+DemoCourse',
            course_completed=True,
            sap_completed_timestamp=1486755998,
            completed_timestamp=datetime.datetime.fromtimestamp(1486755998),
            instructor_name='Professor Professorson',
            grade='Pass',
            enterprise_customer_uuid=self.enterprise_customer.uuid,
            plugin_configuration_id=self.enterprise_config.id,
        )
        transmitter = learner_data.SapSuccessFactorsLearnerTransmitter(self.enterprise_config)
        transmitter.transmit(self.exporter([payload]))
        self.create_course_completion_mock.assert_called_with(payload.sapsf_user_id, payload.serialize())
        assert payload.status == '500'
        assert payload.error_message == 'error occurred'
        assert payload.is_transmitted is False

    def _incomplete_payload(self, grade, progress_status):
        """
        Build a not-completed payload for the enrollment under test.
        """
        return SapSuccessFactorsLearnerDataTransmissionAudit(
            enterprise_course_enrollment_id=self.enterprise_course_enrollment.id,
            sapsf_user_id='sap_user',
            course_id='course-v1:edX+DemoX+DemoCourse',
            course_completed=False,
            sap_completed_timestamp=1486755998,
            completed_timestamp=datetime.datetime.fromtimestamp(1486755998),
            grade=grade,
            progress_status=progress_status,
            enterprise_customer_uuid=self.enterprise_customer.uuid,
            plugin_configuration_id=self.enterprise_config.id,
        )

    @override_switch(ENABLE_FAILED_GRADE_TRANSMISSION_SWITCH, active=True)
    def test_transmit_failed_grade(self):
        """
        A failed grade is transmitted as not completed and saved, so it shows as Failed in sync history.
        """
        self.create_course_completion_mock.return_value = 200, '{"success":"true"}'
        payload = self._incomplete_payload('Fail', 'Failed')
        transmitter = learner_data.SapSuccessFactorsLearnerTransmitter(self.enterprise_config)
        transmitter.transmit(self.exporter([payload]))
        self.create_course_completion_mock.assert_called_once_with(payload.sapsf_user_id, payload.serialize())
        assert '"courseCompleted": "false"' in payload.serialize()
        assert payload.is_transmitted is True
        assert SapSuccessFactorsLearnerDataTransmissionAudit.objects.get(id=payload.id).progress_status == 'Failed'

    def test_skip_failed_grade_when_switch_inactive(self):
        """
        A failed grade is not transmitted while the waffle switch is off.
        """
        payload = self._incomplete_payload('Fail', 'Failed')
        transmitter = learner_data.SapSuccessFactorsLearnerTransmitter(self.enterprise_config)
        transmitter.transmit(self.exporter([payload]))
        self.create_course_completion_mock.assert_not_called()
        assert payload.id is None

    @override_switch(ENABLE_FAILED_GRADE_TRANSMISSION_SWITCH, active=True)
    def test_skip_in_progress_grade(self):
        """
        A grade that is neither passing nor failed is still not transmitted.
        """
        payload = self._incomplete_payload('In Progress', 'In Progress')
        transmitter = learner_data.SapSuccessFactorsLearnerTransmitter(self.enterprise_config)
        transmitter.transmit(self.exporter([payload]))
        self.create_course_completion_mock.assert_not_called()
        assert payload.id is None

    @ddt.data(
        # (new grade, new course_completed, expect transmission)
        ('Pass', True, True),
        ('Fail', False, False),
    )
    @ddt.unpack
    @override_switch(ENABLE_FAILED_GRADE_TRANSMISSION_SWITCH, active=True)
    def test_retransmit_after_failed_grade(self, grade, course_completed, expect_transmission):
        """
        A learner whose failed grade was transmitted is transmitted again once they pass, but not
        while they are still failing.
        """
        self.create_course_completion_mock.return_value = 200, '{"success":"true"}'
        payload = self._incomplete_payload('Fail', 'Failed')
        payload.is_transmitted = True
        payload.save()

        payload.grade = grade
        payload.course_completed = course_completed
        transmitter = learner_data.SapSuccessFactorsLearnerTransmitter(self.enterprise_config)
        transmitter.transmit(self.exporter([payload]))

        assert self.create_course_completion_mock.called is expect_transmission
        assert SapSuccessFactorsLearnerDataTransmissionAudit.objects.get(id=payload.id).grade == grade

    @override_switch(ENABLE_FAILED_GRADE_TRANSMISSION_SWITCH, active=True)
    def test_failed_pass_transmission_after_failed_grade_is_retried(self):
        """
        If the passing grade that follows a transmitted failed grade errors, the single record is
        overwritten as not transmitted, and the passing grade is retried on the next run.
        """
        payload = self._incomplete_payload('Fail', 'Failed')
        payload.is_transmitted = True
        payload.save()
        payload.grade, payload.course_completed, payload.progress_status = 'Pass', True, 'Passed'
        transmitter = learner_data.SapSuccessFactorsLearnerTransmitter(self.enterprise_config)

        self.create_course_completion_mock.side_effect = ClientError('error occurred', 400)
        transmitter.transmit(self.exporter([payload]))
        record = SapSuccessFactorsLearnerDataTransmissionAudit.objects.get(id=payload.id)
        assert (record.grade, record.is_transmitted, record.status) == ('Pass', False, '400')

        self.create_course_completion_mock.side_effect = None
        self.create_course_completion_mock.return_value = 200, '{"success":"true"}'
        transmitter.transmit(self.exporter([record]))
        assert self.create_course_completion_mock.call_count == 2
        assert SapSuccessFactorsLearnerDataTransmissionAudit.objects.get(id=payload.id).is_transmitted is True

    @ddt.data(
        ('user account is inactive', False),
        ('meh, usual network problem', True)
    )
    @ddt.unpack
    def test_transmit_failure_user_inactive(self, content, ecu_active_expectation):
        """Learner data transmission fails because the user is inactive on the SAPSF side, so we mark them inactive
        internally."""
        self.create_course_completion_mock.side_effect = ClientError(content)
        payload = SapSuccessFactorsLearnerDataTransmissionAudit(
            enterprise_course_enrollment_id=self.enterprise_course_enrollment.id,
            sapsf_user_id='sap_user',
            course_id='course-v1:edX+DemoX+DemoCourse',
            course_completed=True,
            sap_completed_timestamp=1486755998,
            completed_timestamp=datetime.datetime.fromtimestamp(1486755998),
            instructor_name='Professor Professorson',
            grade='Pass',
            enterprise_customer_uuid=self.enterprise_customer.uuid,
            plugin_configuration_id=self.enterprise_config.id,
        )
        transmitter = learner_data.SapSuccessFactorsLearnerTransmitter(self.enterprise_config)
        transmitter.transmit(self.exporter([payload]))
        self.create_course_completion_mock.assert_called_with(payload.sapsf_user_id, payload.serialize())
        self.enterprise_customer_user.refresh_from_db()
        assert self.enterprise_customer_user.active == ecu_active_expectation
        assert payload.status == '500'
        assert payload.error_message == content

    def test_transmit_by_course_key_success(self):
        """
        This tests the case where the transmission with the course key succeeds, and as a result
        the transmission with the course run id does not get attempted.
        """
        self.create_course_completion_mock.return_value = 200, '{"success":"true"}'
        payloads = [
            SapSuccessFactorsLearnerDataTransmissionAudit(
                enterprise_course_enrollment_id=self.enterprise_course_enrollment.id,
                sapsf_user_id='sap_user',
                course_id='edX+DemoX',
                course_completed=True,
                sap_completed_timestamp=1486755998,
                completed_timestamp=datetime.datetime.fromtimestamp(1486755998),
                instructor_name='Professor Professorson',
                grade='Pass',
                enterprise_customer_uuid=self.enterprise_customer.uuid,
                plugin_configuration_id=self.enterprise_config.id,
            ),
            SapSuccessFactorsLearnerDataTransmissionAudit(
                enterprise_course_enrollment_id=self.enterprise_course_enrollment.id,
                sapsf_user_id='sap_user',
                course_id='course-v1:edX+DemoX+DemoCourse',
                course_completed=True,
                sap_completed_timestamp=1486755998,
                completed_timestamp=datetime.datetime.fromtimestamp(1486755998),
                instructor_name='Professor Professorson',
                grade='Pass',
                enterprise_customer_uuid=self.enterprise_customer.uuid,
                plugin_configuration_id=self.enterprise_config.id,
            )
        ]
        transmitter = learner_data.SapSuccessFactorsLearnerTransmitter(self.enterprise_config)
        transmitter.transmit(self.exporter(payloads))
        self.create_course_completion_mock.assert_called_once()
        self.create_course_completion_mock.assert_called_with(payloads[0].sapsf_user_id, payloads[0].serialize())

        assert payloads[0].status == '200'
        assert payloads[0].error_message == ''
        assert not payloads[1].status

    def test_transmit_by_course_id_success(self):
        """
        This tests the case where the transmission with the course key fails, and as a result
        the transmission with the course run id is sent as well and succeeds.
        """
        self.create_course_completion_mock.side_effect = [
            ClientError('error occurred'),
            (200, '{"success":"true"}')
        ]
        payloads = [
            SapSuccessFactorsLearnerDataTransmissionAudit(
                enterprise_course_enrollment_id=self.enterprise_course_enrollment.id,
                sapsf_user_id='sap_user',
                course_id='edX+DemoX',
                course_completed=True,
                sap_completed_timestamp=1486755998,
                completed_timestamp=datetime.datetime.fromtimestamp(1486755998),
                instructor_name='Professor Professorson',
                grade='Pass',
                enterprise_customer_uuid=self.enterprise_customer.uuid,
                plugin_configuration_id=self.enterprise_config.id,
            ),
            SapSuccessFactorsLearnerDataTransmissionAudit(
                enterprise_course_enrollment_id=self.enterprise_course_enrollment.id,
                sapsf_user_id='sap_user',
                course_id='course-v1:edX+DemoX+DemoCourse',
                course_completed=True,
                sap_completed_timestamp=1486755998,
                completed_timestamp=datetime.datetime.fromtimestamp(1486755998),
                instructor_name='Professor Professorson',
                grade='Pass',
                enterprise_customer_uuid=self.enterprise_customer.uuid,
                plugin_configuration_id=self.enterprise_config.id,
            )
        ]
        transmitter = learner_data.SapSuccessFactorsLearnerTransmitter(self.enterprise_config)
        transmitter.transmit(self.exporter(payloads))
        expected_calls = [
            mock.call(payloads[0].sapsf_user_id, payloads[0].serialize()),
            mock.call(payloads[1].sapsf_user_id, payloads[1].serialize()),
        ]
        self.create_course_completion_mock.assert_has_calls(expected_calls)

        assert payloads[0].status == '500'
        assert payloads[0].error_message == 'error occurred'
        assert payloads[1].status == '200'
        assert payloads[1].error_message == ''

    def test_override_channel_settings(self):
        """
        If you add any settings to the ChannelSettingsMixin, add a test here for the common default value
        """
        transmitter = learner_data.SapSuccessFactorsLearnerTransmitter(self.enterprise_config)
        assert transmitter.INCLUDE_GRADE_FOR_COMPLETION_AUDIT_CHECK is False
        assert transmitter.TRANSMIT_FAILED_GRADES is True
        assert transmitter.transmit_failed_grades is False
        with override_switch(ENABLE_FAILED_GRADE_TRANSMISSION_SWITCH, active=True):
            assert transmitter.transmit_failed_grades is True
