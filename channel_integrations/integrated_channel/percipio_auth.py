"""
Percipio OAuth2 authentication client.

Fetches and caches short-lived bearer tokens from the Percipio token endpoint
using the OAuth2 client credentials grant flow.

Credentials (PERCIPIO_CLIENT_ID, PERCIPIO_CLIENT_SECRET) are global/shared
across all enterprise customers and are read from Django settings and stored as
environment variables in edx-internal.

Token endpoint URLs differ by geographic region:
  - US / OTHER → https://oauth2-provider.percipio.com/
  - EU         → https://euc1-prod-oauth2-provider.percipio.com/
"""
import logging

import requests
from django.conf import settings
from django.core.cache import cache

LOGGER = logging.getLogger(__name__)

# Default production token endpoints keyed by EnterpriseWebhookConfiguration.region
DEFAULT_PERCIPIO_TOKEN_URLS = {
    'US': 'https://oauth2-provider.percipio.com/oauth2-provider/token',
    'EU': 'https://euc1-prod-oauth2-provider.percipio.com/oauth2-provider/token',
    # OTHER default to the US endpoint
    'OTHER': 'https://oauth2-provider.percipio.com/oauth2-provider/token',
}

_CACHE_KEY_TEMPLATE = 'percipio_auth_token_{region}'

# Fetch a fresh token this many seconds before the reported expiry to avoid
# racing the clock and sending a request with an already-expired token.
_TOKEN_EXPIRY_BUFFER_SECONDS = 60


class PercipioAuthClient:
    """
    Retrieves OAuth2 bearer tokens from the Percipio token endpoint.

    Tokens are cached per region in the Django cache backend so that a new
    HTTP round-trip to Percipio is only made when the cached token has
    expired (or is about to expire).

    Usage::

        token = PercipioAuthClient().get_token('US')
        headers['Authorization'] = f'Bearer {token}'
    """

    def get_token(self, region: str) -> str:
        """
        Return a valid bearer token for *region*.

        Returns the cached token when one exists and has not expired;
        otherwise fetches a new token from the Percipio endpoint, caches it,
        and returns it.

        Args:
            region: One of 'US', 'EU', 'UK', 'OTHER' — matches the
                ``region`` field on ``EnterpriseWebhookConfiguration``.

        Returns:
            A bearer token string suitable for use in an Authorization header.

        Raises:
            requests.HTTPError: If the Percipio token endpoint returns a
                non-2xx response.
            KeyError: If the token response body is missing ``access_token``
                or ``expires_in``.
        """
        cache_key = _CACHE_KEY_TEMPLATE.format(region=region)
        cached_token = cache.get(cache_key)
        if cached_token:
            LOGGER.debug('[Percipio] Using cached auth token for region %s', region)
            return cached_token

        LOGGER.info('[Percipio] Fetching new auth token for region %s', region)
        access_token, expires_in = self._fetch_token(region)

        # Cache the token until just before it expires so we never hand out a
        # token that is about to become invalid.
        ttl = max(0, expires_in - _TOKEN_EXPIRY_BUFFER_SECONDS)
        cache.set(cache_key, access_token, timeout=ttl)

        return access_token

    def _fetch_token(self, region: str) -> tuple:
        """
        POST to the Percipio OAuth2 token endpoint and return the token.

        Args:
            region: Geographic region string used to select the correct
                token endpoint URL.

        Returns:
            A (access_token, expires_in) tuple where *expires_in* is an
            integer number of seconds until expiry.

        Raises:
            requests.HTTPError: On a non-2xx HTTP response.
            KeyError: If ``access_token`` or ``expires_in`` are absent from
                the response JSON.
        """
        client_id = getattr(settings, 'PERCIPIO_CLIENT_ID', '')
        client_secret = getattr(settings, 'PERCIPIO_CLIENT_SECRET', '')

        # Allow the token URL mapping to be overridden in settings for
        # staging / test environments.
        token_urls = getattr(settings, 'PERCIPIO_TOKEN_URLS', DEFAULT_PERCIPIO_TOKEN_URLS)
        url = token_urls.get(region, token_urls.get('US', DEFAULT_PERCIPIO_TOKEN_URLS['US']))

        LOGGER.debug('[Percipio] POSTing to token endpoint %s for region %s', url, region)

        response = requests.post(
            url,
            json={
                'client_id': client_id,
                'client_secret': client_secret,
                'grant_type': 'client_credentials',
                'scope': 'api',
            },
            headers={'Content-Type': 'application/json'},
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        return data['access_token'], data['expires_in']
