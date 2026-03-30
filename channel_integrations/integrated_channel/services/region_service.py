"""
Service for determining user region from SSO metadata.
"""
import logging

from enterprise.models import EnterpriseCustomerUser
from social_django.models import UserSocialAuth

log = logging.getLogger(__name__)

# EU Country Codes (GDPR region)
EU_COUNTRIES = {
    'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR',
    'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL',
    'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE'
}


def get_user_region(user) -> str:
    """
    Extract user region from SSO metadata with fallback strategy.

    Priority:
    1. third_party_auth.UserSocialAuth.extra_data['country'] -> map to region
    2. EnterpriseCustomerUser.data_sharing_consent_records (last resort)
    3. Default to 'OTHER'

    Args:
        user: Django User instance

    Returns:
        str: One of 'US', 'EU', 'OTHER'
    """
    try:
        log.info(f'[Region] Starting region detection for user {user.id}')

        # Priority 1: SSO metadata in extra_data
        social_auth = UserSocialAuth.objects.filter(user=user).first()
        if not social_auth:
            log.info(f'[Region] No social auth record found for user {user.id}')
        elif not social_auth.extra_data:
            log.info(f'[Region] Social auth extra_data is empty for user {user.id}')

        if social_auth and social_auth.extra_data:
            # Auth metadata values can be provided as one-item arrays.
            # Prefer country first for region routing.
            country_code = _extract_metadata_value(social_auth.extra_data.get('country'))
            if country_code:
                region = _map_country_to_region(country_code)
                log.info(
                    f'[Region] Resolved user {user.id} via SSO country: '
                    f'country={country_code} region={region}'
                )

            log.info(f'[Region] No usable SSO country metadata for user {user.id}')

        # Priority 2: Check enterprise customer location (if available)
        ecu = EnterpriseCustomerUser.objects.filter(user_id=user.id, active=True).first()
        if not ecu:
            log.info(f'[Region] No active enterprise customer user record found for user {user.id}')

        if ecu and hasattr(ecu.enterprise_customer, 'country'):
            country_code = ecu.enterprise_customer.country
            region = _map_country_to_region(country_code)
            log.info(
                f'[Region] Resolved user {user.id} via enterprise country: '
                f'country={country_code} region={region}'
            )
            log.info(f'[Region] User {user.id} using enterprise country {country_code} -> {region}')
            return region

        if ecu and not hasattr(ecu.enterprise_customer, 'country'):
            log.info(f'[Region] Enterprise customer has no country attribute for user {user.id}')

    except Exception as e:  # pylint: disable=broad-exception-caught
        log.warning(f'[Region] Error detecting region for user {user.id}: {e}', exc_info=True)

    # Priority 3: Default fallback
    log.info(f'[Region] No region metadata for user {user.id}, defaulting to OTHER')
    return 'OTHER'


def _map_country_to_region(country_code: str) -> str:
    """Map ISO country code to webhook region."""
    # Handle django_countries.Country objects (convert to string code)
    country_code = str(country_code).upper()

    if country_code == 'US':
        return 'US'
    elif country_code == 'EU':
        return 'EU'
    elif country_code in EU_COUNTRIES:
        return 'EU'
    else:
        return 'OTHER'


def _extract_metadata_value(value) -> str:
    """Normalize SSO metadata value to a scalar uppercase string."""
    if isinstance(value, (list, tuple)):
        if not value:
            return ''
        value = value[0]

    normalized = str(value or '').strip().upper()
    return normalized
