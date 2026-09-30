"""
Tests for the SAPSF API Client.
"""

import base64
import datetime
import json
import unittest
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urljoin

import ddt
import pytest
import requests
import responses
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.apps import apps
from freezegun import freeze_time
from pytest import mark, raises

from channel_integrations.exceptions import ClientError
from channel_integrations.sap_success_factors.client import SAPSuccessFactorsAPIClient
from channel_integrations.sap_success_factors.models import (
    SAPAuthType,
    SAPSuccessFactorsEnterpriseCustomerConfiguration,
    SAPSuccessFactorsGlobalConfiguration,
)
from test_utils.factories import EnterpriseCustomerFactory

NOW = datetime.datetime(2017, 1, 2, 3, 4, 5)
# A throwaway key for the self-signed flow, generated once: 2048-bit key generation is slow.
PRIVATE_KEY_PEM = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
).decode()


@ddt.ddt
@mark.django_db
class TestSAPSuccessFactorsAPIClient(unittest.TestCase):
    """
    Test SAPSuccessFactors API methods.
    """

    def setUp(self):
        super().setUp()
        self.oauth_api_path = "learning/oauth-api/rest/v1/token"
        self.oauth_token_api_path = "oauth/token"
        self.completion_status_api_path = "learning/odatav4/public/admin/ocn/v1/current-user/item/learning-event"
        self.course_api_path = "learning/odatav4/public/admin/ocn/v1/OcnCourses"
        self.url_base = "https://test.successfactors.com/"
        self.client_id = "client_id"
        self.client_secret = "client_secret"
        self.company_id = "company_id"
        self.user_id = "user_id"
        self.user_type = "user"
        self.expires_in = 1800
        self.access_token = "access_token"
        self.content_payload = {
            "ocnCourses": [
                {
                    "courseID": "TED1",
                    "providerID": "TED",
                    "status": "ACTIVE",
                    "title": [
                        {
                            "locale": "English",
                            "value": "Can a computer write poetry?"
                        }
                    ]
                }
            ]
        }

        SAPSuccessFactorsGlobalConfiguration.objects.create(
            completion_status_api_path=self.completion_status_api_path,
            course_api_path=self.course_api_path,
            oauth_api_path=self.oauth_api_path,
            oauth_token_api_path=self.oauth_token_api_path,
        )

        self.expected_token_response_body = {"expires_in": self.expires_in, "access_token": self.access_token}
        self.enterprise_config = SAPSuccessFactorsEnterpriseCustomerConfiguration(
            encrypted_key=self.client_id,
            sapsf_base_url=self.url_base,
            sapsf_company_id=self.company_id,
            sapsf_user_id=self.user_id,
            encrypted_secret=self.client_secret,
            active=True,
            decrypted_private_key=PRIVATE_KEY_PEM,
            saml_assertion_audience="sap.example.com",
        )
        self.enterprise_config.enterprise_customer = EnterpriseCustomerFactory()
        self.completion_payload = {
            "userID": "abc123",
            "courseID": "course-v1:ColumbiaX+DS101X+1T2016",
            "providerID": "EDX",
            "courseCompleted": "true",
            "completedTimestamp": 1485283526,
            "instructorName": "Professor Professorson",
            "grade": "Pass"
        }

    def _use_auth_type(self, auth_type):
        """
        Switch the configuration to ``auth_type`` and return the URL its token requests go to.
        """
        self.enterprise_config.auth_type = auth_type
        if auth_type == SAPAuthType.SELF_SIGNED_ASSERTION:
            return self.url_base + self.oauth_token_api_path
        return self.url_base + self.oauth_api_path

    @responses.activate
    @freeze_time(NOW)
    @ddt.data(SAPAuthType.SAP_SIGNED_ASSERTION, SAPAuthType.SELF_SIGNED_ASSERTION)
    def test_get_access_token(self, auth_type):
        token_url = self._use_auth_type(auth_type)
        self.enterprise_config.save()
        expected_response = (self.access_token, NOW + datetime.timedelta(seconds=self.expires_in))

        responses.add(
            responses.POST,
            token_url,
            json=self.expected_token_response_body,
            status=200
        )

        actual_response = SAPSuccessFactorsAPIClient(self.enterprise_config).get_access_token('learner-42', 'admin')
        assert actual_response == expected_response
        assert len(responses.calls) == 1
        assert responses.calls[0].request.url == token_url
        if auth_type == SAPAuthType.SAP_SIGNED_ASSERTION:
            assert json.loads(responses.calls[0].request.body)['scope']['userType'] == 'admin'
            return
        body = parse_qs(responses.calls[0].request.body)
        assert body['grant_type'] == ['urn:ietf:params:oauth:grant-type:saml2-bearer']
        assert (body['client_id'], body['company_id']) == ([self.client_id], [self.company_id])
        assertion = base64.b64decode(body['assertion'][0]).decode('utf-8')
        for expected in ('learner-42', self.enterprise_config.saml_assertion_audience, f'Recipient="{token_url}"'):
            assert expected in assertion
        # Neither the signed assertion nor the live token SAP returned is stored in the API request log.
        log = apps.get_model('channel_integration', 'IntegratedChannelAPIRequestLogs').objects.get(endpoint=token_url)
        assert json.loads(log.payload)['assertion'] == log.response_body == '[REDACTED]'

    @responses.activate
    @ddt.data(SAPAuthType.SAP_SIGNED_ASSERTION, SAPAuthType.SELF_SIGNED_ASSERTION)
    def test_get_access_token_rejects_a_failed_or_malformed_response(self, auth_type):
        """
        A failed response keeps its status, even with a token-shaped body. A malformed 2xx fails with a 502, not
        the upstream 2xx: the learner transmitter reads a status below 300 as a successful send.
        """
        token_url = self._use_auth_type(auth_type)
        token = self.expected_token_response_body
        for status, body, expected_status in (
            (200, {"issuedFor": "learning_public_api"}, 502),
            (200, ["access_token"], 502),
            *((200, {**token, "access_token": value}, 502) for value in (None, "", "   ", 12345)),
            *((200, {**token, "expires_in": value}, 502) for value in (0, -1, True, False, None, 10 ** 20, 1e400)),
            *((status, token, status) for status in (302, 401, 500)),
        ):
            with self.subTest(status=status, body=body):
                responses.reset()
                responses.add(responses.POST, token_url, json=body, status=status)
                with raises(ClientError) as raised:
                    SAPSuccessFactorsAPIClient(self.enterprise_config).get_access_token(self.user_id, self.user_type)
                assert raised.value.status_code == expected_status

    @responses.activate
    def test_get_oauth_access_token_response_non_json(self):
        """ Test  get_oauth_access_token with non json type response"""
        with raises(ClientError):
            responses.add(
                responses.POST,
                urljoin(self.url_base, self.oauth_api_path),
            )
            SAPSuccessFactorsAPIClient(self.enterprise_config).get_oauth_access_token(
                self.client_id,
                self.client_secret,
                self.company_id,
                self.user_id,
                self.user_type,
                self.enterprise_config.enterprise_customer.uuid
            )

    @responses.activate
    @ddt.data(
        ('', None), ('   ', None), ('?tenant=x', None), ('#token', None), ('oauth/token#fragment', None),
        ('https://other-host.example.com/token', None), ('//other-host.example.com/token', None),
        ('oauth/token', 'not-a-valid-pem-key'),
    )
    @ddt.unpack
    def test_get_saml_bearer_access_token_sends_nothing_unsafe(self, oauth_token_api_path, private_key):
        """
        ``urljoin`` lets an absolute or scheme-relative token path replace the SAP base URL, which would send the
        signed assertion to another host, and resolves one with no path to the base URL itself. A fragment is never
        sent but would be embedded in the assertion's Recipient, which SAP rejects. None of these, nor an unusable
        key, may send a request.
        """
        SAPSuccessFactorsGlobalConfiguration.objects.create(oauth_token_api_path=oauth_token_api_path)
        self.enterprise_config.decrypted_private_key = private_key or PRIVATE_KEY_PEM
        with raises(ClientError):
            SAPSuccessFactorsAPIClient(self.enterprise_config).get_saml_bearer_access_token(self.user_id)
        assert not responses.calls

    @responses.activate
    def test_get_saml_bearer_access_token_does_not_follow_redirects(self):
        """
        A 307/308 re-POSTs the body wherever it points, so following one would forward the signed assertion to a
        host the token-path guard never vetted.
        """
        token_url = self._use_auth_type(SAPAuthType.SELF_SIGNED_ASSERTION)
        responses.add(responses.POST, token_url, status=307, headers={'Location': 'https://other-host.example.com/'})
        responses.add(responses.POST, 'https://other-host.example.com/', json=self.expected_token_response_body)
        with raises(ClientError):
            SAPSuccessFactorsAPIClient(self.enterprise_config).get_saml_bearer_access_token(self.user_id)
        assert [call.request.url for call in responses.calls] == [token_url]

    @responses.activate
    @ddt.data(SAPAuthType.SAP_SIGNED_ASSERTION, SAPAuthType.SELF_SIGNED_ASSERTION)
    def test_send_completion_status(self, auth_type):
        token_url = self._use_auth_type(auth_type)
        responses.add(
            responses.POST,
            token_url,
            json=self.expected_token_response_body,
            status=200
        )

        expected_response_body = {"success": "true", "completion_status": self.completion_payload}

        responses.add(
            responses.POST,
            self.url_base + self.completion_status_api_path,
            json=expected_response_body,
            status=200
        )

        expected_response = 200, json.dumps(expected_response_body)

        sap_client = SAPSuccessFactorsAPIClient(self.enterprise_config)
        sap_client._call_post_with_user_override = MagicMock(side_effect=sap_client._call_post_with_user_override)  # pylint: disable=protected-access
        sap_client.get_access_token = MagicMock(side_effect=sap_client.get_access_token)
        # ``get_remote_id()`` can return a number; the token is requested for its string form.
        actual_response = sap_client.create_course_completion(99, json.dumps(self.completion_payload))

        assert actual_response == expected_response
        assert len(responses.calls) == 2
        assert responses.calls[0].request.url == token_url
        expected_url = self.url_base + self.completion_status_api_path
        assert responses.calls[1].request.url == expected_url
        sap_client._call_post_with_user_override.assert_called()  # pylint: disable=protected-access
        sap_client.get_access_token.assert_called_once_with('99', self.enterprise_config.USER_TYPE_USER)

    @responses.activate
    def test_failed_completion_reporting_exception_handling(self):
        responses.add(
            responses.POST,
            self.url_base + self.oauth_api_path,
            json=self.expected_token_response_body,
            status=200
        )

        expected_error_json = {'Error': 'An error has occurred.'}
        expected_error_message = 'SAPSuccessFactorsAPIClient request failed with status 500: {}'.format(
            json.dumps(expected_error_json)
        )
        expected_error_status_code = 500
        responses.add(
            responses.POST,
            self.url_base + self.completion_status_api_path,
            json=expected_error_json,
            status=expected_error_status_code
        )

        sap_client = SAPSuccessFactorsAPIClient(self.enterprise_config)

        with pytest.raises(ClientError) as client_error:
            sap_client.create_course_completion(self.user_type, json.dumps(self.completion_payload))
        assert client_error.value.message == expected_error_message
        assert client_error.value.status_code == expected_error_status_code

        assert len(responses.calls) == 2

    @responses.activate
    @ddt.data('create_content_metadata', 'update_content_metadata', 'delete_content_metadata')
    def test_content_import(self, client_method):
        responses.add(
            responses.POST,
            self.url_base + self.oauth_api_path,
            json=self.expected_token_response_body,
            status=200
        )

        expected_course_response_body = self.content_payload
        expected_course_response_body["@odata.context"] = "$metadata#OcnCourses/$entity"

        responses.add(
            responses.POST,
            self.url_base + self.course_api_path,
            json=expected_course_response_body,
            status=200
        )

        sap_client = SAPSuccessFactorsAPIClient(self.enterprise_config)
        getattr(sap_client, client_method)(self.content_payload)
        assert len(responses.calls) == 2
        assert responses.calls[0].request.url == self.url_base + self.oauth_api_path
        assert responses.calls[1].request.url == self.url_base + self.course_api_path

    @responses.activate
    def test_sap_api_connection_error(self):
        """
        ``create_content_metadata`` should NOT raise ClientError when API request fails with a connection error.
        """
        responses.add(
            responses.POST,
            self.url_base + self.oauth_api_path,
            json=self.expected_token_response_body,
            status=200
        )

        expected_course_response_body = self.content_payload
        expected_course_response_body["@odata.context"] = "$metadata#OcnCourses/$entity"

        responses.add(
            responses.POST,
            self.url_base + self.course_api_path,
            body=requests.exceptions.RequestException()
        )

        with raises(requests.exceptions.RequestException):
            sap_client = SAPSuccessFactorsAPIClient(self.enterprise_config)
            sap_client.create_content_metadata(self.content_payload)

    @responses.activate
    def test_sap_api_application_error(self):
        """
        ``create_content_metadata`` should raise ClientError when API request fails with an application error.
        """
        responses.add(
            responses.POST,
            self.url_base + self.oauth_api_path,
            json=self.expected_token_response_body,
            status=200
        )

        expected_course_response_body = self.content_payload
        expected_course_response_body["@odata.context"] = "$metadata#OcnCourses/$entity"

        responses.add(
            responses.POST,
            self.url_base + self.course_api_path,
            json={'message': 'error'},
            status=400
        )

        sap_client = SAPSuccessFactorsAPIClient(self.enterprise_config)
        status, _ = sap_client.create_content_metadata(self.content_payload)
        assert status >= 400

    @responses.activate
    @freeze_time(NOW)
    @ddt.data(SAPAuthType.SAP_SIGNED_ASSERTION, SAPAuthType.SELF_SIGNED_ASSERTION)
    def test_expired_access_token(self, auth_type):
        """
           If our token expires after some call, make sure to get it again.

           Make a call with a token that expires in 1s, inside the refresh safety margin (time is frozen),
           and make a call again and notice 2 OAuth calls in total are required.
        """
        token_url = self._use_auth_type(auth_type)
        expired_token_response_body = {"expires_in": 1, "access_token": self.access_token}
        responses.add(
            responses.POST,
            token_url,
            json=expired_token_response_body,
            status=200
        )
        expected_course_response_body = self.content_payload
        expected_course_response_body["@odata.context"] = "$metadata#OcnCourses/$entity"

        responses.add(
            responses.POST,
            self.url_base + self.course_api_path,
            json=expected_course_response_body,
            status=200
        )

        sap_client = SAPSuccessFactorsAPIClient(self.enterprise_config)
        sap_client.create_content_metadata(self.content_payload)
        sap_client.create_content_metadata(self.content_payload)
        assert len(responses.calls) == 4
        assert responses.calls[0].request.url == token_url
        assert responses.calls[1].request.url == self.url_base + self.course_api_path
        assert responses.calls[2].request.url == token_url
        assert responses.calls[3].request.url == self.url_base + self.course_api_path

    @responses.activate
    @ddt.data(SAPAuthType.SAP_SIGNED_ASSERTION, SAPAuthType.SELF_SIGNED_ASSERTION)
    def test_client_uses_prevent_learner_submit_flag(self, auth_type):
        responses.add(
            responses.POST,
            self._use_auth_type(auth_type),
            json=self.expected_token_response_body,
            status=200
        )

        sap_client = SAPSuccessFactorsAPIClient(self.enterprise_config)
        sap_client.enterprise_configuration.prevent_self_submit_grades = True

        expected_response_body = {"success": "true", "completion_status": self.completion_payload}
        expected_completion_url = self.url_base + sap_client.GENERIC_COURSE_COMPLETION_PATH

        responses.add(
            responses.POST,
            expected_completion_url,
            json=expected_response_body,
            status=200
        )

        expected_response = 200, json.dumps(expected_response_body)
        # Mimic the transformation behaviour in the client since we expect that to occur when the post is called
        expected_payload = self.completion_payload.copy()
        expected_payload['courseCompleted'] = True
        expected_payload = json.dumps(expected_payload)

        payload = json.dumps(self.completion_payload)

        sap_client._call_post_with_session = MagicMock(side_effect=sap_client._call_post_with_session)  # pylint: disable=protected-access
        actual_response = sap_client.create_course_completion(self.user_type, payload)
        assert actual_response == expected_response

        sap_client._call_post_with_session.assert_called_with(expected_completion_url, expected_payload)  # pylint: disable=protected-access

    @responses.activate
    def test_sync_content_metadata_success(self):
        """
        Test that the sync content metadata method works as expected
        """
        responses.add(
            responses.POST,
            self.url_base + self.oauth_api_path,
            json=self.expected_token_response_body,
            status=200
        )

        expected_course_response_body = self.content_payload
        expected_course_response_body["@odata.context"] = "$metadata#OcnCourses/$entity"

        responses.add(
            responses.POST,
            self.url_base + self.course_api_path,
            json=expected_course_response_body,
            status=200
        )

        sap_client = SAPSuccessFactorsAPIClient(self.enterprise_config)
        status, body = sap_client._sync_content_metadata(self.content_payload)  # pylint: disable=protected-access
        assert status == 200
        assert json.loads(body) == expected_course_response_body
        assert len(responses.calls) == 2

    @responses.activate
    def test_sync_content_metadata_too_many_requests(self):
        """
        Test that the sync content metadata method retries when it gets a 429 response.
        """
        responses.add(
            responses.POST,
            self.url_base + self.oauth_api_path,
            json=self.expected_token_response_body,
            status=200
        )

        responses.add(
            responses.POST,
            self.url_base + self.course_api_path,
            status=429
        )

        sap_client = SAPSuccessFactorsAPIClient(self.enterprise_config)
        with freeze_time(NOW):
            status, body = sap_client._sync_content_metadata(self.content_payload)  # pylint: disable=protected-access,unused-variable
        assert status == 429
        assert len(responses.calls) == sap_client.MAX_RETRIES + 1 + 1  # 1 for the auth call

    @responses.activate
    def test_sync_content_metadata_bad_request(self):
        """
        Test that the sync content metadata method returns the response body when it gets a 400 response.
        """
        responses.add(
            responses.POST,
            self.url_base + self.oauth_api_path,
            json=self.expected_token_response_body,
            status=200
        )

        responses.add(
            responses.POST,
            self.url_base + self.course_api_path,
            json={"message": "error"},
            status=400
        )

        sap_client = SAPSuccessFactorsAPIClient(self.enterprise_config)
        status, body = sap_client._sync_content_metadata(self.content_payload)  # pylint: disable=protected-access
        assert status == 400
        assert json.loads(body) == {'message': 'error'}
        assert len(responses.calls) == 2

    @responses.activate
    def test_sync_content_metadata_retry_logic(self):
        """
        Test that the sync content metadata method retries when it gets a 429 response and then succeeds.
        """
        responses.add(
            responses.POST,
            self.url_base + self.oauth_api_path,
            json=self.expected_token_response_body,
            status=200
        )

        responses.add(
            responses.POST,
            self.url_base + self.course_api_path,
            status=429
        )

        responses.add(
            responses.POST,
            self.url_base + self.course_api_path,
            json=self.content_payload,
            status=200
        )

        sap_client = SAPSuccessFactorsAPIClient(self.enterprise_config)
        with freeze_time(NOW):
            status, body = sap_client._sync_content_metadata(self.content_payload)  # pylint: disable=protected-access
        assert status == 200
        assert json.loads(body) == self.content_payload
        assert len(responses.calls) == 3
