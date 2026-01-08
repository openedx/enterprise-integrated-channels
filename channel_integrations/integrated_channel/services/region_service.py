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
    1. third_party_auth.UserSocialAuth.extra_data['region'] (explicit)
    2. third_party_auth.UserSocialAuth.extra_data['country'] -> map to region
    3. EnterpriseCustomerUser.data_sharing_consent_records (last resort)
    4. Default to 'OTHER'

    Args:
        user: Django User instance

    Returns:
        str: One of 'US', 'EU', 'UK', 'OTHER'
    """
    try:
        # Priority 1: Explicit region in SSO extra_data
        social_auth = UserSocialAuth.objects.filter(user=user).first()
        if social_auth and social_auth.extra_data:
            # Check for explicit region
            explicit_region = social_auth.extra_data.get('region')
            if explicit_region in ['US', 'EU', 'UK', 'OTHER']:
                log.debug(f'[Region] User {user.id} has explicit region: {explicit_region}')
                return explicit_region

            # Priority 2: Map country code to region
            country_code = social_auth.extra_data.get('country')
            if country_code:
                region = _map_country_to_region(country_code)
                log.debug(f'[Region] User {user.id} mapped from country {country_code} to {region}')
                return region

        # Priority 3: Check enterprise customer location (if available)
        ecu = EnterpriseCustomerUser.objects.filter(user=user, active=True).first()
        if ecu and hasattr(ecu.enterprise_customer, 'country'):
            country_code = ecu.enterprise_customer.country
            region = _map_country_to_region(country_code)
            log.debug(f'[Region] User {user.id} using enterprise country {country_code} -> {region}')
            return region

    except Exception as e:  # pylint: disable=broad-exception-caught
        log.warning(f'[Region] Error detecting region for user {user.id}: {e}')

    # Priority 4: Default fallback
    log.info(f'[Region] No region metadata for user {user.id}, defaulting to OTHER')
    return 'OTHER'


def _map_country_to_region(country_code: str) -> str:
    """Map ISO country code to webhook region."""
    country_code = country_code.upper()

    if country_code == 'US':
        return 'US'
    elif country_code == 'GB':
        return 'UK'
    elif country_code in EU_COUNTRIES:
        return 'EU'
    else:
        return 'OTHER'
