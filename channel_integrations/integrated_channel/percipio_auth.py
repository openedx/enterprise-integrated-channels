"""
Percipio OAuth2 authentication client.

Fetches and caches short-lived bearer tokens from the Percipio token endpoint
using the OAuth2 client credentials grant flow.

Credentials (client_id, client_secret) are stored per enterprise customer on
the EnterpriseWebhookConfiguration model and passed directly to get_token().

Token endpoint URLs differ by geographic region:
  - US / OTHER → https://oauth2-provider.percipio.com/
  - EU         → https://euc1-prod-oauth2-provider.percipio.com/
"""
import logging

import requests
from django.core.cache import cache
from channel_integrations.integrated_channel.models import EnterpriseWebhookConfiguration

LOGGER = logging.getLogger(__name__)

_CACHE_KEY_TEMPLATE = 'percipio_auth_token_{region}_{client_id}'

# Fetch a fresh token this many seconds before the reported expiry to avoid
# racing the clock and sending a request with an already-expired token.
_TOKEN_EXPIRY_BUFFER_SECONDS = 60


class PercipioAuthHelper:
    """
    Retrieves OAuth2 bearer tokens from the Percipio token endpoint.

    Tokens are cached per region and client_id in the Django cache backend so
    that a new HTTP round-trip to Percipio is only made when the cached token
    has expired (or is about to expire).

    Usage::

        token = PercipioAuthHelper().get_token('US', config)
        headers['Authorization'] = f'Bearer {token}'
    """

    def get_token(self, region: str, config: EnterpriseWebhookConfiguration) -> str:
        """
        Return a valid bearer token for *region*.

        Returns the cached token when one exists and has not expired;
        otherwise fetches a new token from the Percipio endpoint, caches it,
        and returns it.

        Args:
            region: User's region, one of 'US', 'EU', 'OTHER'
            config: EnterpriseWebhookConfiguration

        Returns:
            A bearer token string suitable for use in an Authorization header.

        Raises:
            requests.HTTPError: If the Percipio token endpoint returns a
                non-2xx response.
            KeyError: If the token response body is missing ``access_token``
                or ``expires_in``.
        """
        client_id = config.client_id
        cache_key = _CACHE_KEY_TEMPLATE.format(region=region, client_id=client_id)
        cached_token = cache.get(cache_key)
        if cached_token:
            LOGGER.debug('[Percipio] Using cached auth token for region %s', region)
            return cached_token

        LOGGER.info('[Percipio] Fetching new auth token for region %s', region)
        access_token, expires_in = self._fetch_token(region, config)

        # Cache the token until just before it expires so we never hand out a
        # token that is about to become invalid.
        ttl = max(0, expires_in - _TOKEN_EXPIRY_BUFFER_SECONDS)
        cache.set(cache_key, access_token, timeout=ttl)

        return access_token

    def _fetch_token(self, region: str, config: EnterpriseWebhookConfiguration) -> tuple:
        """
        POST to the Percipio OAuth2 token endpoint and return the token.

        Args:
            region: Geographic region string used to select the correct
                token endpoint URL.
            config: EnterpriseWebhookConfiguration containing the token
                endpoint URL and OAuth2 credentials.

        Returns:
            A (access_token, expires_in) tuple where *expires_in* is an
            integer number of seconds until expiry.

        Raises:
            requests.HTTPError: On a non-2xx HTTP response.
            KeyError: If ``access_token`` or ``expires_in`` are absent from
                the response JSON.
        """
        url = config.webhook_url

        LOGGER.debug('[Percipio] POSTing to token endpoint %s for region %s', url, region)

        response = requests.post(
            url,
            json={
                'client_id': config.client_id,
                'client_secret': config.decrypted_client_secret,
                'grant_type': 'client_credentials',
                'scope': 'api',
            },
            headers={'Content-Type': 'application/json'},
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        return data['access_token'], data['expires_in']
