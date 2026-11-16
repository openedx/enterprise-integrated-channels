"""
Tests for SAPSF learner data exporters.
"""

import datetime
import unittest
from unittest import mock
from unittest.mock import MagicMock, Mock

import ddt
from pytest import mark
from waffle.testutils import override_switch

from django.db.utils import IntegrityError

from channel_integrations.integrated_channel.channel_settings import ENABLE_FAILED_GRADE_TRANSMISSION_SWITCH
from channel_integrations.sap_success_factors.exporters.learner_data import SapSuccessFactorsLearnerExporter
from channel_integrations.sap_success_factors.models import SapSuccessFactorsLearnerDataTransmissionAudit
from test_utils.factories import (
    EnterpriseCourseEnrollmentFactory,
    EnterpriseCustomerFactory,
    EnterpriseCustomerUserFactory,
    SAPSuccessFactorsEnterpriseCustomerConfigurationFactory,
    UserFactory,
)


@mark.django_db
@ddt.ddt
class TestSAPSuccessFactorLearnerDataExporter(unittest.TestCase):
    """
    Tests for the ``SapSuccessFactorsLearnerDataExporter`` class.
    """

    def setUp(self):
        super().setUp()
        self.enterprise_customer = EnterpriseCustomerFactory()
        self.enterprise_customer_user = EnterpriseCustomerUserFactory(
            enterprise_customer=self.enterprise_customer,
        )
        self.enterprise_course_enrollment = EnterpriseCourseEnrollmentFactory(
            id=5,
            enterprise_customer_user=self.enterprise_customer_user,
        )
        self.enterprise_config = SAPSuccessFactorsEnterpriseCustomerConfigurationFactory(
            enterprise_customer=self.enterprise_customer,
            decrypted_key="client_id",
            sapsf_base_url="http://test.successfactors.com/",
            sapsf_company_id="company_id",
            sapsf_user_id="user_id",
            decrypted_secret="client_secret"
        )

    def test_unique_enrollment_id_course_id_constraint(self):
        """
        Ensure that the unique constraint on enterprise_course_enrollment_id and course_id is enforced.
        """
        course_id = 'course-v1:edX+DemoX+DemoCourse'
        SapSuccessFactorsLearnerDataTransmissionAudit.objects.create(
            enterprise_course_enrollment_id=self.enterprise_course_enrollment.id,
            sapsf_user_id='sap_user',
            course_id=course_id,
            course_completed=True,
            sap_completed_timestamp=1486755998,
            completed_timestamp=datetime.datetime.fromtimestamp(1486755998),
            instructor_name='Professor Professorson',
            grade='Pass',
            enterprise_customer_uuid=self.enterprise_customer.uuid,
            plugin_configuration_id=self.enterprise_config.id,
        )
        with self.assertRaises(IntegrityError):
            SapSuccessFactorsLearnerDataTransmissionAudit.objects.create(
                enterprise_course_enrollment_id=self.enterprise_course_enrollment.id,
                sapsf_user_id='sap_user',
                course_id=course_id,
                course_completed=True,
                sap_completed_timestamp=1486755998,
                completed_timestamp=datetime.datetime.fromtimestamp(1486755998),
                instructor_name='Professor Professorson',
                grade='Pass',
                enterprise_customer_uuid=self.enterprise_customer.uuid,
                plugin_configuration_id=self.enterprise_config.id,
            )

    @mock.patch('channel_integrations.sap_success_factors.exporters.learner_data.get_course_id_for_enrollment')
    @mock.patch('channel_integrations.sap_success_factors.exporters.learner_data.get_course_run_for_enrollment')
    def test_call_get_remote_id(self, mock_get_course_run_for_enrollment, mock_get_course_id_for_enrollment):
        mock_get_course_run_for_enrollment.return_value = MagicMock()
        mock_get_course_id_for_enrollment.return_value = 'test:id'
        user = UserFactory()
        completed_date = None
        grade = 'Pass'
        course_completed = False
        enterprise_enrollment = EnterpriseCourseEnrollmentFactory(
            enterprise_customer_user=self.enterprise_customer_user
        )
        enterprise_enrollment.enterprise_customer_user.get_remote_id = MagicMock()
        exporter = SapSuccessFactorsLearnerExporter(user, self.enterprise_config)

        exporter.get_learner_data_records(
            enterprise_enrollment,
            completed_date,
            grade,
            course_completed
        )
        enterprise_enrollment.enterprise_customer_user.get_remote_id.assert_called_once_with(
            self.enterprise_config.idp_id
        )

    @mock.patch('channel_integrations.sap_success_factors.exporters.learner_data.get_course_id_for_enrollment')
    @mock.patch('channel_integrations.sap_success_factors.exporters.learner_data.get_course_run_for_enrollment')
    def test_retrieve_same_learner_data_record(
            self,
            mock_get_course_run_for_enrollment,
            mock_get_course_id_for_enrollment,
    ):
        """
        If a learner data record already exists for the enrollment, it should be retrieved instead of created.
        """
        mock_get_course_run_for_enrollment.return_value = MagicMock()
        mock_get_course_id_for_enrollment.return_value = 'test:id'
        user = UserFactory()
        completed_date = None
        grade = 'Pass'
        progress_status = 'Passed'
        course_completed = False
        enterprise_enrollment = EnterpriseCourseEnrollmentFactory(
            enterprise_customer_user=self.enterprise_customer_user
        )
        enterprise_enrollment.enterprise_customer_user.get_remote_id = Mock(return_value=99)
        exporter = SapSuccessFactorsLearnerExporter(user, self.enterprise_config)
        learner_data_records_1 = exporter.get_learner_data_records(
            enterprise_enrollment,
            completed_date,
            grade,
            course_completed,
            progress_status
        )[0]
        learner_data_records_1.save()
        learner_data_records_2 = exporter.get_learner_data_records(
            enterprise_enrollment,
            completed_date,
            grade,
            course_completed,
            progress_status
        )[0]
        learner_data_records_2.save()

        assert enterprise_enrollment.enterprise_customer_user.get_remote_id.call_count == 2
        assert learner_data_records_1.id == learner_data_records_2.id

    @mock.patch('channel_integrations.sap_success_factors.exporters.learner_data.get_course_id_for_enrollment')
    @mock.patch('channel_integrations.sap_success_factors.exporters.learner_data.get_course_run_for_enrollment')
    def test_existing_record_refreshed_with_current_data(
            self,
            mock_get_course_run_for_enrollment,
            mock_get_course_id_for_enrollment,
    ):
        """
        An existing record is refreshed with current data, so a retry never resends a stale SAP user ID or grade.
        """
        mock_get_course_run_for_enrollment.return_value = MagicMock()
        mock_get_course_id_for_enrollment.return_value = 'test:id'
        stale_record = SapSuccessFactorsLearnerDataTransmissionAudit.objects.create(
            enterprise_course_enrollment_id=self.enterprise_course_enrollment.id,
            sapsf_user_id='stale_user',
            course_id='test:id',
            course_completed=True,
            grade='Pass',
            progress_status='Passed',
            status='400',
            enterprise_customer_uuid=self.enterprise_customer.uuid,
            plugin_configuration_id=self.enterprise_config.id,
        )
        self.enterprise_customer_user.get_remote_id = Mock(return_value='current_user')
        completed_date = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        exporter = SapSuccessFactorsLearnerExporter(UserFactory(), self.enterprise_config)

        record = exporter.get_learner_data_records(
            self.enterprise_course_enrollment,
            completed_date=completed_date,
            grade='Fail',
            content_title='Demo Course',
            progress_status='Failed',
            course_completed=False,
        )[0]

        assert record.id == stale_record.id
        assert record.sapsf_user_id == 'current_user'
        assert record.grade == 'Fail'
        assert record.progress_status == 'Failed'
        assert record.course_completed is False
        assert record.completed_timestamp == completed_date
        assert record.sap_completed_timestamp == 1767225600000
        assert record.content_title == 'Demo Course'

    @ddt.data(
        # (latest transmitted grade, expect the enrollment to be exported again)
        ('Fail', True),
        ('Pass', False),
    )
    @ddt.unpack
    @override_switch(ENABLE_FAILED_GRADE_TRANSMISSION_SWITCH, active=True)
    def test_filter_out_pre_transmitted_enrollments(self, transmitted_grade, expect_included):
        """
        Enrollments with a transmitted failed grade are exported again so a later pass can be sent;
        enrollments with any other transmitted grade are not.
        """
        SapSuccessFactorsLearnerDataTransmissionAudit.objects.create(
            enterprise_course_enrollment_id=self.enterprise_course_enrollment.id,
            sapsf_user_id='sap_user',
            course_id='test:id',
            grade=transmitted_grade,
            is_transmitted=True,
            enterprise_customer_uuid=self.enterprise_customer.uuid,
            plugin_configuration_id=self.enterprise_config.id,
        )
        exporter = SapSuccessFactorsLearnerExporter(UserFactory(), self.enterprise_config)

        included = exporter._filter_out_pre_transmitted_enrollments(  # pylint: disable=protected-access
            [self.enterprise_course_enrollment],
            'SAP',
            None,
            SapSuccessFactorsLearnerDataTransmissionAudit,
        )

        assert (self.enterprise_course_enrollment in included) is expect_included

    def test_override_of_default_channel_settings(self):
        """
        If you override any settings to the ChannelSettingsMixin, add a test here for those
        """
        user = UserFactory()
        exporter = SapSuccessFactorsLearnerExporter(user, self.enterprise_config)
        assert exporter.INCLUDE_GRADE_FOR_COMPLETION_AUDIT_CHECK is False
        assert exporter.TRANSMIT_FAILED_GRADES is True
        assert exporter.transmit_failed_grades is False
        with override_switch(ENABLE_FAILED_GRADE_TRANSMISSION_SWITCH, active=True):
            assert exporter.transmit_failed_grades is True
