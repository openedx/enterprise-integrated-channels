"""Tests for ic_transmit_learner_data management command."""

from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase

from test_utils import factories

MODULE_PATH = 'channel_integrations.integrated_channel.management.commands.ic_transmit_learner_data.'


class TestICTransmitLearnerDataCommand(TestCase):
    """Tests for command argument handling and force-transmit routing."""

    def setUp(self):
        super().setUp()
        self.api_user = factories.UserFactory(username='api-user')
        self.enterprise_customer = factories.EnterpriseCustomerFactory(active=True)
        self.enterprise_customer_user = factories.EnterpriseCustomerUserFactory(
            user_id=self.api_user.id,
            enterprise_customer=self.enterprise_customer,
        )
        self.enrollment = factories.EnterpriseCourseEnrollmentFactory(
            enterprise_customer_user=self.enterprise_customer_user,
            course_id='course-v1:edX+DemoX+DemoCourse',
        )
        self.channel_config = factories.Degreed2EnterpriseCustomerConfigurationFactory(
            enterprise_customer=self.enterprise_customer,
            active=True,
        )

    def test_force_requires_enterprise_enrollment_id(self):
        """Using --force without --enterprise_enrollment_id should fail fast."""
        with self.assertRaisesRegex(CommandError, 'requires --enterprise_enrollment_id'):
            call_command(
                'ic_transmit_learner_data',
                '--api_user', self.api_user.username,
                '--channel', 'DEGREED2',
                '--force',
            )

    def test_invalid_enterprise_enrollment_id_raises_error(self):
        """Unknown enterprise enrollment id should raise CommandError."""
        with self.assertRaisesRegex(CommandError, 'was not found'):
            call_command(
                'ic_transmit_learner_data',
                '--api_user', self.api_user.username,
                '--channel', 'DEGREED2',
                '--enterprise_enrollment_id', '999999',
            )

    @mock.patch(MODULE_PATH + 'transmit_learner_data.delay')
    def test_force_mode_enqueues_task_with_force_and_enrollment(self, mock_delay):
        """Force transmit should enqueue task with enrollment id and force flag."""
        with mock.patch(
            MODULE_PATH + 'Command.get_integrated_channels',
            return_value=[self.channel_config],
        ):
            call_command(
                'ic_transmit_learner_data',
                '--api_user', self.api_user.username,
                '--channel', 'DEGREED2',
                '--enterprise_enrollment_id', str(self.enrollment.id),
                '--force',
            )

        mock_delay.assert_called_once_with(
            username=self.api_user.username,
            channel_code=self.channel_config.channel_code(),
            channel_pk=self.channel_config.pk,
            enterprise_enrollment_id=self.enrollment.id,
            force_transmit=True,
        )
