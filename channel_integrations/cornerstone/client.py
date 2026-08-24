"""
Client for connecting to Cornerstone.
"""

import base64
import json
import logging
import time
from urllib.parse import urljoin

import requests
from django.apps import apps
from django.conf import settings

from channel_integrations.cornerstone.utils import get_or_create_key_pair
from channel_integrations.exceptions import ClientError
from channel_integrations.integrated_channel.client import IntegratedChannelApiClient
from channel_integrations.utils import generate_formatted_log, refresh_session_if_expired

LOGGER = logging.getLogger(__name__)


class CornerstoneAPIClient(IntegratedChannelApiClient):
    """
    Client for connecting to Cornerstone.

    Specifically, this class supports obtaining access tokens
    and posting user's course completion status to progress endpoints.
    """

    # Fallback used when CornerstoneGlobalConfiguration.oauth_api_path is not set.
    DEFAULT_OAUTH_API_PATH = '/services/api/oauth2/token'

    # Cornerstone's Transcript API endpoint for marking a learner's transcript complete.
    TRANSCRIPT_COMPLETE_API_PATH = getattr(
        settings,
        'ENTERPRISE_CORNERSTONE_TRANSCRIPT_COMPLETE_PATH',
        '/services/api/v1/transcripts/complete',
    )

    # Cornerstone's Learning Assignments API endpoint for looking up/updating a learner's
    # in-progress assignment record.
    LEARNING_ASSIGNMENTS_API_PATH = getattr(
        settings,
        'ENTERPRISE_CORNERSTONE_LEARNING_ASSIGNMENTS_PATH',
        '/services/api/v1/LearningAssignments',
    )

    # Scope requested when minting a completion-writing access token. Covers both the Transcript
    # API (completions) and the Learning Assignments API (in-progress updates).
    COMPLETION_SCOPE = getattr(
        settings,
        'ENTERPRISE_CORNERSTONE_OAUTH_SCOPE',
        'transcript:update learningassignment:read learningassignment:update',
    )

    def __init__(self, enterprise_configuration):
        """
        Instantiate a new client.

        Args:
            enterprise_configuration (CornerstoneEnterpriseCustomerConfiguration): An enterprise customers's
            configuration model for connecting with Cornerstone
        """
        super().__init__(enterprise_configuration)
        self.global_cornerstone_config = apps.get_model(
            'cornerstone_channel',
            'CornerstoneGlobalConfiguration'
        ).current()
        self.session = None
        self.expires_at = None

    def create_content_metadata(self, serialized_data):
        """
        Create content metadata using the Cornerstone course content API.
        Since Cornerstone is following pull content model we don't need to implement this method
        """
        return 200, ''

    def update_content_metadata(self, serialized_data):
        """
        Update content metadata using the Cornerstone course content API.
        Since Cornerstone is following pull content model we don't need to implement this method
        """
        return 200, ''

    def delete_content_metadata(self, serialized_data):
        """
        Delete content metadata using the Cornerstone course content API.
        Since Cornerstone is following pull content model we don't need to implement this method
        """
        return 200, ''

    def delete_course_completion(self, user_id, payload):
        """
        Delete a completion status previously sent to the Cornerstone Completion Status endpoint
        Cornerstone does not support this.
        """
        return 200, ''

    def cleanup_duplicate_assignment_records(self, courses):
        """
        Not implemented yet.
        """
        LOGGER.error(
            generate_formatted_log(
                self.enterprise_configuration.channel_code(),
                self.enterprise_configuration.enterprise_customer.uuid,
                None,
                None,
                "Cornerstone integrated channel does not yet support assignment deduplication."
            )
        )

    def create_course_completion(self, user_id, payload):
        """
        Send a learner's completion to Cornerstone.

        Routed one of two ways, depending on whether the customer has been migrated:

        - Transcript API (migrated): PATCH the learner's transcript with an OAuth access token we
          mint and refresh ourselves. No dependency on the learner's launch-time session token.
        - Completion callback (legacy): POST to the callback URL Cornerstone gave us at launch,
          authenticated with the session token from that same launch. That token expires in roughly
          two hours and we cannot refresh it, so completions sent later than that get a 401 back.

        Raises:
            HTTPError: if we received a failure response code from Cornerstone
        """
        json_payload = json.loads(payload)
        data = json_payload['data']
        if self.enterprise_configuration.uses_oauth_completion_auth:
            if data.get('status') == 'Completed':
                return self._complete_transcript(data)
            return self._update_learning_assignment(data)
        return self._post_completion_callback(data)

    def _complete_transcript(self, data):
        """
        Mark a learner's transcript complete through Cornerstone's Transcript API.

        Args:
            data (dict): the serialized audit record.

        Returns: (status_code, response_text)
        """
        url = urljoin(
            self.enterprise_configuration.cornerstone_base_url,
            self.TRANSCRIPT_COMPLETE_API_PATH,
        )
        transcript_payload = {
            'userGuid': data.get('userGuid'),
            'learningObjectId': self._get_learning_object_id(data.get('courseId')),
            'ignoreWorkflow': True,
        }

        self._create_session()
        start_time = time.time()
        response = self.session.patch(url, json=transcript_payload)
        duration_seconds = time.time() - start_time
        self._store_api_call(url, transcript_payload, duration_seconds, response)
        return response.status_code, response.text

    def _get_learning_object_id(self, course_id):
        """
        Return the identifier Cornerstone knows this course by.

        Cornerstone builds its learning objects by pulling our course-list feed, where each course
        is published under ``CornerstoneCourseKey.external_course_id``. That is the only identifier
        shared between the two systems, so it is what we key the transcript update on.

        If Cornerstone turns out to require its own internally-generated learning object GUID
        instead, this is the single place that needs to grow a lookup against their learning object
        API, plus somewhere to cache the result.
        """
        return get_or_create_key_pair(course_id).external_course_id

    def _update_learning_assignment(self, data):
        """
        Update a learner's in-progress assignment through Cornerstone's Learning Assignments API.

        The Transcript API only understands completions, so in-progress records are sent here
        instead: first resolving the assignment ID for this learner/course pair, then patching
        its status and last-accessed date.

        Args:
            data (dict): the serialized audit record.

        Returns: (status_code, response_text)
        """
        self._create_session()

        learning_object_id = self._get_learning_object_id(data.get('courseId'))
        lookup_url = urljoin(
            self.enterprise_configuration.cornerstone_base_url,
            self.LEARNING_ASSIGNMENTS_API_PATH,
        )
        start_time = time.time()
        lookup_response = self.session.get(
            lookup_url,
            params={
                'userId': data.get('userGuid'),
                'loId': learning_object_id,
            },
        )
        duration_seconds = time.time() - start_time
        self._store_api_call(lookup_url, {'userId': data.get('userGuid'), 'loId': learning_object_id},
                              duration_seconds, lookup_response)

        if not lookup_response.ok:
            return lookup_response.status_code, lookup_response.text

        try:
            assignment_id = lookup_response.json()[0]['assignmentId']
        except (KeyError, IndexError, ValueError):
            LOGGER.info(
                generate_formatted_log(
                    self.enterprise_configuration.channel_code(),
                    self.enterprise_configuration.enterprise_customer.uuid,
                    None,
                    data.get('courseId'),
                    'Skipping learning assignment update: no assignment found for userGuid '
                    '{user_guid} and learning object {lo_id}.'.format(
                        user_guid=data.get('userGuid'), lo_id=learning_object_id
                    )
                )
            )
            return 200, ''

        update_url = urljoin(
            self.enterprise_configuration.cornerstone_base_url,
            '{path}/{assignment_id}'.format(
                path=self.LEARNING_ASSIGNMENTS_API_PATH, assignment_id=assignment_id
            ),
        )
        assignment_payload = {
            'Status': data.get('status'),
            'LastAccessDate': data.get('completionDate'),
        }
        start_time = time.time()
        response = self.session.patch(update_url, json=assignment_payload)
        duration_seconds = time.time() - start_time
        self._store_api_call(update_url, assignment_payload, duration_seconds, response)
        return response.status_code, response.text

    def _post_completion_callback(self, data):
        """
        Legacy path: POST the completion to the callback URL captured at course launch.

        Used for customers who have not been given OAuth credentials yet. Authenticated with the
        launch-time session token, which is why it fails once that token ages out.

        Args:
            data (dict): the serialized audit record.

        Returns: (status_code, response_text)
        """
        callback_url = data.pop('callbackUrl')
        session_token = self.enterprise_configuration.session_token
        if not session_token:
            session_token = data.pop('sessionToken')

        # When exporting content metadata, we encode course keys that contain invalid chars or
        # set them to uuids to comply with Cornerstone standards
        data['courseId'] = self._get_learning_object_id(data.get('courseId'))

        url = '{base_url}{callback_url}{completion_path}?sessionToken={session_token}'.format(
            base_url=self.enterprise_configuration.cornerstone_base_url,
            callback_url=callback_url,
            completion_path=self.global_cornerstone_config.completion_status_api_path,
            session_token=session_token,
        )
        start_time = time.time()
        response = requests.post(
            url,
            json=[data],
            headers={
                'Authorization': self.authorization_header,
                'Content-Type': 'application/json'
            }
        )
        duration_seconds = time.time() - start_time
        self._store_api_call(url, data, duration_seconds, response)
        return response.status_code, response.text

    def _store_api_call(self, url, payload, duration_seconds, response):
        """
        Record an outbound call against the customer's API request log.
        """
        IntegratedChannelAPIRequestLogs = apps.get_model(
            "channel_integration", "IntegratedChannelAPIRequestLogs"
        )
        IntegratedChannelAPIRequestLogs.store_api_call(
            enterprise_customer=self.enterprise_configuration.enterprise_customer,
            enterprise_customer_configuration_id=self.enterprise_configuration.id,
            endpoint=url,
            payload=json.dumps(payload),
            time_taken=duration_seconds,
            status_code=response.status_code,
            response_body=response.text,
            channel_name=self.enterprise_configuration.channel_code()
        )

    def create_assessment_reporting(self, user_id, payload):
        """
        Not implemented yet
        """

    def get_oauth_url(self):
        """
        Full URL of the customer's Cornerstone token endpoint.
        """
        oauth_api_path = self.global_cornerstone_config.oauth_api_path or self.DEFAULT_OAUTH_API_PATH
        return urljoin(self.enterprise_configuration.cornerstone_base_url, oauth_api_path)

    def _create_session(self):
        """
        Instantiate a new session object for use in connecting with Cornerstone.

        Reuses the existing session until its access token is due to expire, then mints a new one.
        """
        self.session, self.expires_at = refresh_session_if_expired(
            self._get_oauth_access_token,
            self.session,
            self.expires_at,
        )

    def _get_oauth_access_token(self):
        """
        Retrieve an OAuth 2.0 access token using the client credentials grant.

        Returns:
            tuple: access token string and its lifetime in seconds.

        Raises:
            ClientError: If Cornerstone returned a response we could not read a token out of.
        """
        config = self.enterprise_configuration
        url = self.get_oauth_url()
        data = {
            'grant_type': 'client_credentials',
            'scope': self.COMPLETION_SCOPE,
            'client_id': config.decrypted_client_id,
            'client_secret': config.decrypted_client_secret,
        }
        start_time = time.time()
        response = requests.post(
            url,
            data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        duration_seconds = time.time() - start_time
        IntegratedChannelAPIRequestLogs = apps.get_model(
            "channel_integration", "IntegratedChannelAPIRequestLogs"
        )
        IntegratedChannelAPIRequestLogs.store_api_call(
            enterprise_customer=config.enterprise_customer,
            enterprise_customer_configuration_id=config.id,
            endpoint=url,
            # Neither the request nor the response body is stored verbatim: one carries the client
            # secret, the other the access token. Failures keep their body, which is what we debug on.
            payload=json.dumps({'grant_type': data['grant_type'], 'scope': data['scope']}),
            time_taken=duration_seconds,
            status_code=response.status_code,
            response_body='<access token redacted>' if response.ok else response.text,
            channel_name=config.channel_code()
        )

        try:
            token_response = response.json()
            return token_response['access_token'], token_response.get('expires_in')
        except (KeyError, ValueError) as error:
            raise ClientError(
                'CornerstoneAPIClient failed to obtain an OAuth access token from {url}: '
                'status_code={status_code}'.format(url=url, status_code=response.status_code),
                status_code=response.status_code,
            ) from error

    @property
    def authorization_header(self):
        """
        Authorization header for authenticating requests to cornerstone progress API.
        """
        return 'Basic {}'.format(
            base64.b64encode('{key}:{secret}'.format(
                key=self.global_cornerstone_config.key, secret=self.global_cornerstone_config.secret
            ).encode('utf-8')).decode()
        )
