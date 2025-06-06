"""
Test for xAPI utility functions.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from faker import Factory as FakerFactory
from pytest import mark

from channel_integrations.exceptions import ClientError
from channel_integrations.xapi.client import EnterpriseXAPIClient
from channel_integrations.xapi.utils import (
    is_success_response,
    send_course_completion_statement,
    send_course_enrollment_statement,
)
from test_utils import factories

MODULE_PATH = 'channel_integrations.xapi.utils.'


@mark.django_db
class TestUtils(unittest.TestCase):
    """
    Tests for the xAPI Utility Functions.
    """

    def setUp(self):
        super().setUp()
        self.faker = FakerFactory.create()

        self.user = factories.UserFactory()
        self.user.profile = mock.Mock(country=mock.Mock(code='PK'))
        self.mock_social_auth = mock.Mock(provider='tpa-saml', uid='default:edxsso')
        self.mock_save_statement_success = mock.Mock(
            name='response',
            response=mock.Mock(name='response', status=200)
        )

        now = datetime.now()

        self.course_overview_mock_data = {
            'id': self.faker.text(max_nb_chars=25),  # pylint: disable=no-member
            'display_name': self.faker.text(max_nb_chars=25),  # pylint: disable=no-member
            'short_description': self.faker.text(),  # pylint: disable=no-member
            'marketing_url': self.faker.url(),  # pylint: disable=no-member
            'effort': self.faker.text(max_nb_chars=10),  # pylint: disable=no-member
            'start': now,
            'end': now + timedelta(weeks=3, days=4),
            'course_key': 'OrgX+Course101',
            'course_uuid': 'b1e7c719af3c42288c6f50e2124bb913',
        }
        self.course_overview = mock.Mock(**self.course_overview_mock_data)

        self.course_enrollment = mock.Mock(user=self.user, course=self.course_overview)
        self.course_grade = mock.Mock(percent_grade=0.80, passed_timestamp='2020-04-01')

        self.x_api_lrs_config = factories.XAPILRSConfigurationFactory()
        self.x_api_client = EnterpriseXAPIClient(self.x_api_lrs_config)

    @mock.patch('channel_integrations.xapi.client.RemoteLRS', mock.MagicMock())
    @mock.patch('channel_integrations.xapi.utils.get_user_social_auth')
    @mock.patch('enterprise.api_client.client.JwtBuilder')
    @mock.patch('enterprise.api_client.discovery.get_api_data')
    def test_send_course_enrollment_statement(self, mock_get_user_social_auth, *args):
        """
        Verify that send_course_enrollment_statement sends xAPI statement to LRS.
        """
        mock_get_user_social_auth.return_value = self.mock_social_auth

        send_course_enrollment_statement(
            self.x_api_lrs_config,
            self.user,
            self.course_overview,
            'course',
            {'status': 500, 'error_messages': None},
        )

        # Pylint has no way of knowing that the returned value here is a mock, so it assumes it cannot have the
        # assert_called attr
        self.x_api_client.lrs.save_statement.assert_called()  # pylint: disable=no-member, useless-suppression

    @mock.patch('channel_integrations.xapi.client.RemoteLRS', mock.MagicMock())
    @mock.patch('enterprise.api_client.client.JwtBuilder')
    @mock.patch('enterprise.api_client.discovery.get_api_data')
    @mock.patch(MODULE_PATH + 'EnterpriseXAPIClient')
    @mock.patch('channel_integrations.xapi.utils.get_user_social_auth')
    def test_send_course_enrollment_statement_success(self, mock_get_user_social_auth, mock_xapi_client, *args):
        """
        Verify that send_course_enrollment_statement sends xAPI statement to LRS.
        """
        mock_get_user_social_auth.return_value = self.mock_social_auth
        mock_xapi_client.return_value.save_statement.return_value.response.status = 200

        send_course_enrollment_statement(
            self.x_api_lrs_config,
            self.user,
            self.course_overview,
            'course',
            {'status': 500, 'error_messages': None},
        )

    @mock.patch('channel_integrations.xapi.client.RemoteLRS', mock.MagicMock())
    @mock.patch('enterprise.api_client.client.JwtBuilder')
    @mock.patch('enterprise.api_client.discovery.get_api_data')
    @mock.patch(MODULE_PATH + 'EnterpriseXAPIClient')
    @mock.patch('channel_integrations.xapi.utils.get_user_social_auth')
    def test_send_course_enrollment_statement_client_error(self, mock_get_user_social_auth, mock_xapi_client, *args):
        """
        Verify that send_course_enrollment_statement sends xAPI statement to LRS.
        """
        mock_get_user_social_auth.return_value = self.mock_social_auth
        mock_xapi_client.return_value.save_statement.side_effect = ClientError('EnterpriseXAPIClient request failed.')

        send_course_enrollment_statement(
            self.x_api_lrs_config,
            self.user,
            self.course_overview,
            'course',
            {'status': 500, 'error_messages': None},
        )

    @mock.patch('channel_integrations.xapi.client.RemoteLRS', mock.MagicMock())
    @mock.patch('enterprise.api_client.client.JwtBuilder')
    @mock.patch('enterprise.api_client.discovery.get_api_data')
    @mock.patch('channel_integrations.xapi.utils.get_user_social_auth')
    def test_send_course_completion_statement(self, mock_get_user_social_auth, *args):
        """
        Verify that send_course_completion_statement sends xAPI statement to LRS.
        """
        mock_get_user_social_auth.return_value = self.mock_social_auth
        send_course_completion_statement(
            self.x_api_lrs_config,
            self.user,
            self.course_overview,
            self.course_grade,
            'course',
            {'status': 500, 'error_message': None}
        )

        # Pylint has no way of knowing that the returned value here is a mock, so it assumes it cannot have the
        # assert_called attr
        self.x_api_client.lrs.save_statement.assert_called()  # pylint: disable=no-member, useless-suppression

    def test_is_success_response(self):
        """
        Make sure is_success_response logic works as expected.
        """
        response_fields = {'status': 200, 'error_message': None}
        self.assertTrue(is_success_response(response_fields))

        response_fields = {'status': 400, 'error_message': None}
        self.assertFalse(is_success_response(response_fields))

        response_fields = {'status': 500, 'error_message': None}
        self.assertFalse(is_success_response(response_fields))
