"""
Tests for Degreed2 client for channel_integrations.
"""

import json
import unittest
from urllib.parse import urljoin

import pytest
import responses

from django.apps import apps

from channel_integrations.cornerstone.client import CornerstoneAPIClient
from channel_integrations.cornerstone.utils import get_or_create_key_pair
from channel_integrations.exceptions import ClientError
from test_utils import factories

IntegratedChannelAPIRequestLogs = apps.get_model(
    "channel_integration", "IntegratedChannelAPIRequestLogs"
)


@pytest.mark.django_db
class TestCornerstoneApiClient(unittest.TestCase):
    """
    Test Degreed2 API client methods.
    """

    def setUp(self):
        super().setUp()
        self.cornerstone_base_url = "https://edx.example.com/"
        self.oauth_api_path = "/services/api/oauth2/token"
        self.global_config = factories.CornerstoneGlobalConfigurationFactory(
            oauth_api_path=self.oauth_api_path,
            completion_status_api_path="",
        )
        self.csod_config = factories.CornerstoneEnterpriseCustomerConfigurationFactory(
            cornerstone_base_url=self.cornerstone_base_url
        )

    @responses.activate
    def test_create_course_completion_stores_api_record(self):
        """
        ``create_course_completion`` should use the appropriate URLs for transmission.
        """
        cornerstone_api_client = CornerstoneAPIClient(self.csod_config)
        callbackUrl = "dummy_callback_url"
        sessionToken = "dummy_session_oken"
        payload = {
            "data": {
                "userGuid": "dummy_id",
                "sessionToken": sessionToken,
                "callbackUrl": callbackUrl,
                "subdomain": "dummy_subdomain",
            }
        }
        responses.add(
            responses.POST,
            f"{self.cornerstone_base_url}{callbackUrl}?sessionToken={sessionToken}",
            json="{}",
            status=200,
        )
        assert IntegratedChannelAPIRequestLogs.objects.count() == 0
        output = cornerstone_api_client.create_course_completion(
            "test-learner@example.com", json.dumps(payload)
        )
        assert IntegratedChannelAPIRequestLogs.objects.count() == 1
        assert len(responses.calls) == 1
        assert output == (200, '"{}"')

    def _migrate_config_to_oauth(self):
        """
        Give the config OAuth credentials, which routes completions to the Transcript API.
        """
        self.csod_config.decrypted_client_id = "dummy_client_id"
        self.csod_config.decrypted_client_secret = "dummy_client_secret"
        self.csod_config.save()

    def _transcript_url(self, client):  # pylint: disable=unused-argument
        return urljoin(self.cornerstone_base_url, self.csod_config.transcript_complete_api_path)

    @staticmethod
    def _completion_payload(**overrides):
        data = {
            "userGuid": "dummy_guid",
            "courseId": "edX+DemoX",
            "status": "Completed",
            "successStatus": "Pass",
            "sessionToken": "expired_session_token",
            "callbackUrl": "dummy_callback_url",
            "subdomain": "dummy_subdomain",
        }
        data.update(overrides)
        return json.dumps({"data": data})

    @responses.activate
    def test_completion_goes_to_the_transcript_api_once_migrated(self):
        """
        With OAuth credentials configured, a completion should PATCH the Transcript API with a
        bearer token, and carry no session token anywhere.
        """
        self._migrate_config_to_oauth()
        cornerstone_api_client = CornerstoneAPIClient(self.csod_config)
        transcript_url = self._transcript_url(cornerstone_api_client)

        responses.add(
            responses.POST,
            cornerstone_api_client.get_oauth_url(),
            json={"access_token": "dummy_access_token", "expires_in": 3600},
            status=200,
        )
        responses.add(responses.PATCH, transcript_url, json="{}", status=200)

        output = cornerstone_api_client.create_course_completion(
            "test-learner@example.com", self._completion_payload()
        )

        assert output == (200, '"{}"')
        assert len(responses.calls) == 2

        token_request = responses.calls[0]
        transcript_request = responses.calls[1]
        assert "client_credentials" in token_request.request.body
        assert transcript_request.request.method == "PATCH"
        assert transcript_request.request.url == transcript_url
        assert transcript_request.request.headers["Authorization"] == "Bearer dummy_access_token"

        body = json.loads(transcript_request.request.body)
        assert body["userGuid"] == "dummy_guid"
        assert body["ignoreWorkflow"] is True
        # The learning object is keyed on the id we publish in the course-list feed.
        assert body["learningObjectId"] == get_or_create_key_pair("edX+DemoX").external_course_id
        assert "sessionToken" not in body
        assert "sessionToken" not in transcript_request.request.url

        # The token request body and the token itself are kept out of the stored API record.
        token_record = IntegratedChannelAPIRequestLogs.objects.get(endpoint=token_request.request.url)
        assert "dummy_client_secret" not in token_record.payload
        assert "dummy_access_token" not in token_record.response_body

    def _assignments_url(self, client):  # pylint: disable=unused-argument
        return urljoin(self.cornerstone_base_url, self.csod_config.learning_assignments_api_path)

    @responses.activate
    def test_in_progress_records_go_to_the_learning_assignments_api(self):
        """
        In-progress records are routed to the Learning Assignments API rather than the Transcript
        API, since the Transcript API only understands completions.
        """
        self._migrate_config_to_oauth()
        cornerstone_api_client = CornerstoneAPIClient(self.csod_config)
        assignments_url = self._assignments_url(cornerstone_api_client)

        responses.add(
            responses.POST,
            cornerstone_api_client.get_oauth_url(),
            json={"access_token": "dummy_access_token", "expires_in": 3600},
            status=200,
        )
        responses.add(
            responses.GET,
            assignments_url,
            json=[{"assignmentId": "dummy_assignment_id"}],
            status=200,
        )
        responses.add(
            responses.PATCH,
            f"{assignments_url}/dummy_assignment_id",
            json="{}",
            status=200,
        )

        output = cornerstone_api_client.create_course_completion(
            "test-learner@example.com",
            self._completion_payload(status="In Progress", successStatus=None),
        )

        assert output == (200, '"{}"')

        lookup_request = responses.calls[1]
        assert lookup_request.request.method == "GET"
        assert "userId=dummy_guid" in lookup_request.request.url
        assert "loId=" in lookup_request.request.url

        update_request = responses.calls[2]
        assert update_request.request.method == "PATCH"
        assert update_request.request.url == f"{assignments_url}/dummy_assignment_id"
        body = json.loads(update_request.request.body)
        assert body["Status"] == "In Progress"

    @responses.activate
    def test_in_progress_records_raise_when_no_assignment_found(self):
        """
        If Cornerstone has no matching assignment for this learner/course, a ``ClientError`` is
        raised (rather than a forced success) so the transmission stays eligible for retry.
        """
        self._migrate_config_to_oauth()
        cornerstone_api_client = CornerstoneAPIClient(self.csod_config)
        assignments_url = self._assignments_url(cornerstone_api_client)

        responses.add(
            responses.POST,
            cornerstone_api_client.get_oauth_url(),
            json={"access_token": "dummy_access_token", "expires_in": 3600},
            status=200,
        )
        responses.add(
            responses.GET,
            assignments_url,
            json=[],
            status=200,
        )

        with pytest.raises(ClientError) as excinfo:
            cornerstone_api_client.create_course_completion(
                "test-learner@example.com",
                self._completion_payload(status="In Progress", successStatus=None),
            )

        assert excinfo.value.status_code == 404
        assert len(responses.calls) == 2

    @responses.activate
    def test_in_progress_records_propagate_lookup_failures(self):
        """
        If the Learning Assignments lookup itself fails, its status and body are returned as-is
        rather than attempting to resolve an assignment id.
        """
        self._migrate_config_to_oauth()
        cornerstone_api_client = CornerstoneAPIClient(self.csod_config)
        assignments_url = self._assignments_url(cornerstone_api_client)

        responses.add(
            responses.POST,
            cornerstone_api_client.get_oauth_url(),
            json={"access_token": "dummy_access_token", "expires_in": 3600},
            status=200,
        )
        responses.add(
            responses.GET,
            assignments_url,
            json={"error": "server error"},
            status=500,
        )

        output = cornerstone_api_client.create_course_completion(
            "test-learner@example.com",
            self._completion_payload(status="In Progress", successStatus=None),
        )

        assert output == (500, '{"error": "server error"}')
        assert len(responses.calls) == 2

    @responses.activate
    def test_unmigrated_config_still_uses_the_legacy_callback(self):
        """
        A config with no OAuth credentials should keep posting to the launch-time callback URL.
        """
        cornerstone_api_client = CornerstoneAPIClient(self.csod_config)
        responses.add(
            responses.POST,
            f"{self.cornerstone_base_url}dummy_callback_url",
            json="{}",
            status=200,
        )

        output = cornerstone_api_client.create_course_completion(
            "test-learner@example.com", self._completion_payload()
        )

        assert output == (200, '"{}"')
        assert len(responses.calls) == 1
        assert responses.calls[0].request.method == "POST"
        assert "sessionToken=expired_session_token" in responses.calls[0].request.url

    @responses.activate
    def test_create_course_completion_reuses_unexpired_access_token(self):
        """
        A second completion in the same client's lifetime should reuse the existing access token.
        """
        self._migrate_config_to_oauth()
        cornerstone_api_client = CornerstoneAPIClient(self.csod_config)

        responses.add(
            responses.POST,
            cornerstone_api_client.get_oauth_url(),
            json={"access_token": "dummy_access_token", "expires_in": 3600},
            status=200,
        )
        responses.add(
            responses.PATCH,
            self._transcript_url(cornerstone_api_client),
            json="{}",
            status=200,
        )

        cornerstone_api_client.create_course_completion(
            "test-learner@example.com", self._completion_payload()
        )
        cornerstone_api_client.create_course_completion(
            "test-learner@example.com", self._completion_payload()
        )

        token_calls = [
            call for call in responses.calls
            if call.request.url == cornerstone_api_client.get_oauth_url()
        ]
        assert len(token_calls) == 1

    @responses.activate
    def test_get_oauth_access_token_raises_on_unparseable_response(self):
        """
        A token endpoint that does not hand back an ``access_token`` should raise a ``ClientError``.
        """
        self.csod_config.decrypted_client_id = "dummy_client_id"
        self.csod_config.decrypted_client_secret = "dummy_client_secret"
        self.csod_config.save()

        cornerstone_api_client = CornerstoneAPIClient(self.csod_config)
        responses.add(
            responses.POST,
            cornerstone_api_client.get_oauth_url(),
            json={"error": "invalid_client"},
            status=401,
        )

        with pytest.raises(ClientError):
            cornerstone_api_client._get_oauth_access_token()  # pylint: disable=protected-access

        # Failures keep their response body, which is what we debug on.
        token_record = IntegratedChannelAPIRequestLogs.objects.get()
        assert "invalid_client" in token_record.response_body
