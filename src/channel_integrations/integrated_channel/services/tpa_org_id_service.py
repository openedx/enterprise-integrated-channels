"""
Service for extracting a learner's TPA (third-party auth) org id from SSO metadata.
"""
import logging

from social_django.models import UserSocialAuth

from enterprise.tpa_pipeline import get_user_social_auth

log = logging.getLogger(__name__)


def get_tpa_org_id(user, enterprise_customer):
    """
    Extract the org id (e.g. Percipio's `percipioOrganizationUuid`) asserted by a learner's IdP at
    SSO login, or None if unavailable.

    Args:
        user: Django User instance
        enterprise_customer: EnterpriseCustomer instance the learner is logging in under

    Returns:
        str | None
    """
    if not user:
        return None

    try:
        social_auth = _get_social_auth(user, enterprise_customer)
        if not social_auth:
            log.info(f'[OrgGroupSync] No social auth record found for user {user.id}')
            return None
        if not social_auth.extra_data:
            log.info(f'[OrgGroupSync] Social auth extra_data is empty for user {user.id}')
            return None

        tpa_org_id = _normalize_tpa_org_id(social_auth.extra_data.get('percipioOrganizationUuid'))
        if not tpa_org_id:
            log.info(f'[OrgGroupSync] No usable org id in SSO metadata for user {user.id}')
        return tpa_org_id
    except Exception as e:  # pylint: disable=broad-exception-caught
        log.warning(f'[OrgGroupSync] Error extracting org id for user {user.id}: {e}', exc_info=True)
        return None


def _get_social_auth(user, enterprise_customer):
    """
    Prefer edx-enterprise's IdP-aware disambiguation, but never let it regress existing callers
    (e.g. the Percipio webhook path, which worked fine before this disambiguation existed) if it
    can't resolve the customer's identity provider. `get_user_social_auth` raises when an
    enterprise's configured provider_id isn't registered in the third_party_auth Registry -
    falling back to the plain per-user lookup here restores the exact behavior this repo relied
    on before this function existed.
    """
    try:
        social_auth = get_user_social_auth(user, enterprise_customer)
        if social_auth:
            return social_auth
    except Exception as e:  # pylint: disable=broad-exception-caught
        log.warning(
            f'[OrgGroupSync] get_user_social_auth failed for user {user.id}, '
            f'falling back to plain UserSocialAuth lookup: {e}'
        )

    return UserSocialAuth.objects.filter(user=user).first()


def _normalize_tpa_org_id(identifier_value):
    """
    Normalize a TPA org id value to a scalar string (or None).

    SSO metadata sources may provide single-item arrays instead of a scalar value.
    """
    if isinstance(identifier_value, (list, tuple)):
        identifier_value = identifier_value[0] if identifier_value else None
    if identifier_value is None:
        return None
    return str(identifier_value)
