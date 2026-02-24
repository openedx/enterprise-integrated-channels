"""
Tests for the Percipio OAuth2 authentication client.
"""
from unittest.mock import patch, MagicMock

import pytest
import requests
import responses
from django.core.cache import cache
from django.test import override_settings

from channel_integrations.integrated_channel.percipio_auth import (
    DEFAULT_PERCIPIO_TOKEN_URLS,
    PercipioAuthClient,
    _CACHE_KEY_TEMPLATE,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the Django cache before and after every test."""
    cache.clear()
    yield
    cache.clear()


MOCK_TOKEN_RESPONSE = {
    'access_token': 'mock-bearer-token-abc123',
    'expires_in': 3600,
    'token_type': 'Bearer',
}


class TestPercipioAuthClientGetToken:
    """Tests for PercipioAuthClient.get_token."""

    @responses.activate
    @override_settings(
        PERCIPIO_CLIENT_ID='test-client-id',
        PERCIPIO_CLIENT_SECRET='test-client-secret',
    )
    def test_get_token_fetches_when_cache_empty(self):
        """A cache miss causes get_token to fetch from the Percipio endpoint."""
        responses.add(
            responses.POST,
            DEFAULT_PERCIPIO_TOKEN_URLS['US'],
            json=MOCK_TOKEN_RESPONSE,
            status=200,
        )

        client = PercipioAuthClient()
        token = client.get_token('US')

        assert token == 'mock-bearer-token-abc123'
        assert len(responses.calls) == 1

    @responses.activate
    @override_settings(
        PERCIPIO_CLIENT_ID='test-client-id',
        PERCIPIO_CLIENT_SECRET='test-client-secret',
    )
    def test_get_token_returns_cached_token(self):
        """A second call returns the cached token without another HTTP request."""
        responses.add(
            responses.POST,
            DEFAULT_PERCIPIO_TOKEN_URLS['US'],
            json=MOCK_TOKEN_RESPONSE,
            status=200,
        )

        client = PercipioAuthClient()
        first = client.get_token('US')
        second = client.get_token('US')

        assert first == second == 'mock-bearer-token-abc123'
        # Only one real HTTP call should have been made
        assert len(responses.calls) == 1

    @responses.activate
    @override_settings(
        PERCIPIO_CLIENT_ID='test-client-id',
        PERCIPIO_CLIENT_SECRET='test-client-secret',
    )
    def test_get_token_eu_region_uses_eu_url(self):
        """EU region requests hit the EU token endpoint."""
        responses.add(
            responses.POST,
            DEFAULT_PERCIPIO_TOKEN_URLS['EU'],
            json=MOCK_TOKEN_RESPONSE,
            status=200,
        )

        client = PercipioAuthClient()
        token = client.get_token('EU')

        assert token == 'mock-bearer-token-abc123'
        assert responses.calls[0].request.url == DEFAULT_PERCIPIO_TOKEN_URLS['EU']

    @responses.activate
    @override_settings(
        PERCIPIO_CLIENT_ID='test-client-id',
        PERCIPIO_CLIENT_SECRET='test-client-secret',
    )
    def test_get_token_other_region_defaults_to_us_url(self):
        """OTHER region falls back to the US token endpoint."""
        responses.add(
            responses.POST,
            DEFAULT_PERCIPIO_TOKEN_URLS['US'],
            json=MOCK_TOKEN_RESPONSE,
            status=200,
        )

        client = PercipioAuthClient()
        token = client.get_token('OTHER')

        assert responses.calls[0].request.url == DEFAULT_PERCIPIO_TOKEN_URLS['US']
        assert token == 'mock-bearer-token-abc123'

    @responses.activate
    @override_settings(
        PERCIPIO_CLIENT_ID='test-client-id',
        PERCIPIO_CLIENT_SECRET='test-client-secret',
    )
    def test_get_token_caches_with_expiry_buffer(self):
        """Token is cached with a TTL reduced by the expiry buffer."""
        responses.add(
            responses.POST,
            DEFAULT_PERCIPIO_TOKEN_URLS['US'],
            json={**MOCK_TOKEN_RESPONSE, 'expires_in': 120},
            status=200,
        )

        with patch('channel_integrations.integrated_channel.percipio_auth.cache') as mock_cache:
            mock_cache.get.return_value = None  # simulate cache miss
            client = PercipioAuthClient()
            client.get_token('US')

            # TTL should be expires_in (120) minus buffer (60) = 60
            mock_cache.set.assert_called_once_with(
                _CACHE_KEY_TEMPLATE.format(region='US'),
                'mock-bearer-token-abc123',
                timeout=60,
            )

    @responses.activate
    @override_settings(
        PERCIPIO_CLIENT_ID='test-client-id',
        PERCIPIO_CLIENT_SECRET='test-client-secret',
    )
    def test_get_token_raises_on_http_error(self):
        """A non-2xx response from the token endpoint raises HTTPError."""
        responses.add(
            responses.POST,
            DEFAULT_PERCIPIO_TOKEN_URLS['US'],
            json={'error': 'invalid_client'},
            status=401,
        )

        client = PercipioAuthClient()
        with pytest.raises(requests.HTTPError):
            client.get_token('US')


class TestPercipioAuthClientFetchToken:
    """Tests for PercipioAuthClient._fetch_token."""

    @responses.activate
    @override_settings(
        PERCIPIO_CLIENT_ID='my-client-id',
        PERCIPIO_CLIENT_SECRET='my-client-secret',
    )
    def test_fetch_token_sends_correct_payload(self):
        """_fetch_token POSTs the correct JSON body to the token endpoint."""
        responses.add(
            responses.POST,
            DEFAULT_PERCIPIO_TOKEN_URLS['US'],
            json=MOCK_TOKEN_RESPONSE,
            status=200,
        )

        client = PercipioAuthClient()
        access_token, expires_in = client._fetch_token('US')

        assert access_token == 'mock-bearer-token-abc123'
        assert expires_in == 3600

        import json
        sent_body = json.loads(responses.calls[0].request.body)
        assert sent_body == {
            'client_id': 'my-client-id',
            'client_secret': 'my-client-secret',
            'grant_type': 'client_credentials',
            'scope': 'api',
        }

    @responses.activate
    @override_settings(
        PERCIPIO_CLIENT_ID='test-client-id',
        PERCIPIO_CLIENT_SECRET='test-client-secret',
        PERCIPIO_TOKEN_URLS={
            'US': 'https://custom-staging.example.com/token',
            'EU': 'https://custom-staging-eu.example.com/token',
            'OTHER': 'https://custom-staging.example.com/token',
        },
    )
    def test_fetch_token_respects_settings_override(self):
        """PERCIPIO_TOKEN_URLS in settings overrides the default endpoint map."""
        responses.add(
            responses.POST,
            'https://custom-staging.example.com/token',
            json=MOCK_TOKEN_RESPONSE,
            status=200,
        )

        client = PercipioAuthClient()
        client._fetch_token('US')

        assert responses.calls[0].request.url == 'https://custom-staging.example.com/token'

    @responses.activate
    @override_settings(
        PERCIPIO_CLIENT_ID='test-client-id',
        PERCIPIO_CLIENT_SECRET='test-client-secret',
    )
    def test_fetch_token_raises_on_missing_access_token(self):
        """KeyError is raised if the response body omits access_token."""
        responses.add(
            responses.POST,
            DEFAULT_PERCIPIO_TOKEN_URLS['US'],
            json={'expires_in': 3600},  # missing access_token
            status=200,
        )

        client = PercipioAuthClient()
        with pytest.raises(KeyError):
            client._fetch_token('US')
