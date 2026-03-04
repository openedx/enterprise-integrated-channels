"""
Tests for the Percipio OAuth2 authentication client.
"""
# pylint: disable=redefined-outer-name
import json
from unittest.mock import patch

import pytest
import requests
import responses
from django.core.cache import cache

from channel_integrations.integrated_channel.models import EnterpriseWebhookConfiguration
from channel_integrations.integrated_channel.percipio_auth import (
    PercipioAuthHelper,
    _CACHE_KEY_TEMPLATE,
)
from test_utils.factories import EnterpriseCustomerFactory


MOCK_TOKEN_RESPONSE = {
    'access_token': 'mock-bearer-token-abc123',
    'expires_in': 3600,
    'token_type': 'Bearer',
    'scope': 'api',
}

TEST_CLIENT_ID = 'test-client-id'
TEST_CLIENT_SECRET = 'test-client-secret'

TOKEN_URLS = {
    'US': 'https://fake-us-url.example.com/token',
    'EU': 'https://fake-eu-url.example.com/token',
    'OTHER': 'https://fake-develop-url.example.com/token',
}
WEBHOOK_URLS = {
    'US': 'https://fake-us-url.example.com',
    'EU': 'https://fake-eu-url.example.com',
    'OTHER': 'https://fake-develop-url.example.com',
}
REGIONS = ['US', 'EU', 'OTHER']


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the Django cache before and after every test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def percipio_token_configs():
    """Create one EnterpriseWebhookConfiguration per region pointing at the Percipio token endpoints."""
    enterprise = EnterpriseCustomerFactory()
    webhook_configs = {}

    for region in REGIONS:
        webhook_configs[region] = EnterpriseWebhookConfiguration.objects.create(
            enterprise_customer=enterprise,
            region=region,
            webhook_url=WEBHOOK_URLS[region],
            webhook_token_url=TOKEN_URLS[region],
            client_id=TEST_CLIENT_ID,
            decrypted_client_secret=TEST_CLIENT_SECRET,
        )

    return webhook_configs


@pytest.mark.django_db
class TestPercipioAuthHelperGetToken:
    """Tests for PercipioAuthHelper.get_token."""

    @responses.activate
    def test_get_token_fetches_when_cache_empty(self, percipio_token_configs):
        """A cache miss causes get_token to fetch from the Percipio endpoint."""
        responses.add(
            responses.POST,
            TOKEN_URLS['US'],
            json=MOCK_TOKEN_RESPONSE,
            status=200,
        )

        client = PercipioAuthHelper()
        token = client.get_token('US', percipio_token_configs["US"])

        assert token == 'mock-bearer-token-abc123'
        assert len(responses.calls) == 1

    @responses.activate
    def test_get_token_returns_cached_token(self, percipio_token_configs):
        """A second call returns the cached token without another HTTP request."""
        responses.add(
            responses.POST,
            TOKEN_URLS['US'],
            json=MOCK_TOKEN_RESPONSE,
            status=200,
        )

        client = PercipioAuthHelper()
        first = client.get_token('US', percipio_token_configs["US"])
        second = client.get_token('US', percipio_token_configs["US"])

        assert first == second == 'mock-bearer-token-abc123'
        # Only one real HTTP call should have been made
        assert len(responses.calls) == 1

    @responses.activate
    def test_get_token_eu_region_uses_eu_url(self, percipio_token_configs):
        """EU region requests hit the EU token endpoint."""
        responses.add(
            responses.POST,
            TOKEN_URLS['EU'],
            json=MOCK_TOKEN_RESPONSE,
            status=200,
        )

        client = PercipioAuthHelper()
        token = client.get_token('EU', percipio_token_configs["EU"])

        assert token == 'mock-bearer-token-abc123'
        assert responses.calls[0].request.url == TOKEN_URLS['EU']

    @responses.activate
    def test_get_token_caches_with_expiry_buffer(self, percipio_token_configs):
        """Token is cached with a TTL reduced by the expiry buffer."""
        responses.add(
            responses.POST,
            TOKEN_URLS['US'],
            json={**MOCK_TOKEN_RESPONSE, 'expires_in': 120},
            status=200,
        )

        with patch('channel_integrations.integrated_channel.percipio_auth.cache') as mock_cache:
            mock_cache.get.return_value = None  # simulate cache miss
            client = PercipioAuthHelper()
            client.get_token('US', percipio_token_configs["US"])

            # TTL should be expires_in (120) minus buffer (60) = 60
            mock_cache.set.assert_called_once_with(
                _CACHE_KEY_TEMPLATE.format(region='US', client_id=TEST_CLIENT_ID),
                'mock-bearer-token-abc123',
                timeout=60,
            )

    @responses.activate
    def test_get_token_raises_on_http_error(self, percipio_token_configs):
        """A non-2xx response from the token endpoint raises HTTPError."""
        responses.add(
            responses.POST,
            TOKEN_URLS['US'],
            json={'error': 'invalid_client'},
            status=401,
        )
        client = PercipioAuthHelper()
        with pytest.raises(requests.HTTPError):
            client.get_token('US', percipio_token_configs["US"])


@pytest.mark.django_db
class TestPercipioAuthHelperFetchToken:
    """Tests for PercipioAuthHelper._fetch_token."""

    @responses.activate
    def test_fetch_token_sends_correct_payload(self, percipio_token_configs):
        """_fetch_token POSTs the correct JSON body to the token endpoint."""
        responses.add(
            responses.POST,
            TOKEN_URLS['US'],
            json=MOCK_TOKEN_RESPONSE,
            status=200,
        )

        client = PercipioAuthHelper()
        access_token, expires_in = client._fetch_token('US', percipio_token_configs["US"])  # pylint: disable=protected-access

        assert access_token == 'mock-bearer-token-abc123'
        assert expires_in == 3600

        sent_body = json.loads(responses.calls[0].request.body)
        assert sent_body == {
            'client_id': TEST_CLIENT_ID,
            'client_secret': TEST_CLIENT_SECRET,
            'grant_type': 'client_credentials',
            'scope': 'api',
        }

    @responses.activate
    def test_fetch_token_uses_webhook_token_url_from_config(self, percipio_token_configs):
        """_fetch_token uses the webhook_token_url from the matching EnterpriseWebhookConfiguration."""
        custom_url = 'https://custom-staging.example.com/token'
        us_config = percipio_token_configs["US"]
        us_config.webhook_token_url = custom_url
        us_config.save()

        responses.add(
            responses.POST,
            custom_url,
            json=MOCK_TOKEN_RESPONSE,
            status=200,
        )

        client = PercipioAuthHelper()
        client._fetch_token('US', us_config)  # pylint: disable=protected-access

        assert responses.calls[0].request.url == custom_url

    @responses.activate
    def test_fetch_token_raises_on_missing_access_token(self, percipio_token_configs):
        """KeyError is raised if the response body omits access_token."""
        responses.add(
            responses.POST,
            TOKEN_URLS['US'],
            json={'expires_in': 3600},  # missing access_token
            status=200,
        )

        client = PercipioAuthHelper()
        with pytest.raises(KeyError):
            client._fetch_token('US', percipio_token_configs["US"])  # pylint: disable=protected-access
