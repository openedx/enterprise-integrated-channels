"""
Test for xAPI client.
"""

import unittest
from unittest import mock

from pytest import mark, raises

from channel_integrations.exceptions import ClientError
from channel_integrations.xapi.client import EnterpriseXAPIClient
from channel_integrations.xapi.statements.base import EnterpriseStatement
from test_utils import factories


@mark.django_db
class TestXAPILRSConfiguration(unittest.TestCase):
    """
    Tests for the ``XAPILRSConfiguration`` model.
    """

    def setUp(self):
        super().setUp()
        self.x_api_lrs_config = factories.XAPILRSConfigurationFactory()
        self.x_api_client = EnterpriseXAPIClient(self.x_api_lrs_config)
        self.statement = EnterpriseStatement()

    @mock.patch('channel_integrations.xapi.client.RemoteLRS', mock.MagicMock())
    def test_save_statement(self):
        """
        Verify that save_statement sends xAPI statement to LRS.
        """
        # verify that request completes without an error.
        self.x_api_client.save_statement(self.statement)
        self.x_api_client.lrs.save_statement.assert_called_once_with(self.statement)

    @mock.patch('channel_integrations.xapi.client.RemoteLRS', mock.MagicMock())
    def test_save_statement_raises_client_error(self):
        """
        Verify that save_statement raises ClientError if it could not complete request successfully.
        """
        self.x_api_client.lrs.save_statement = mock.Mock(return_value=None)

        with raises(ClientError):
            self.x_api_client.save_statement(self.statement)
