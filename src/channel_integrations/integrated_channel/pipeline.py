"""
Third-party-auth pipeline entry point for TPA org allowlist -> Learner Credit budget group sync.

Registered as a SOCIAL_AUTH_PIPELINE entry in edx-platform, right after
`enterprise.tpa_pipeline.handle_enterprise_logistration`. Runs on every SSO login on the
platform, not just Skillsoft's, so this module carries the outermost safety layer: a waffle
switch (default off) and a broad try/except that never raises. See the "Development spec" in the
ENT-12084 plan for the rollout sequencing this switch is used for.
"""
import logging

import waffle  # pylint: disable=invalid-django-waffle-import

from enterprise.tpa_pipeline import get_enterprise_customer_for_running_pipeline

from channel_integrations.integrated_channel.services.org_group_sync_service import sync_learner_budget_group

log = logging.getLogger(__name__)

ENABLE_TPA_ORG_GROUP_LOGIN_SYNC_SWITCH = 'enable_tpa_org_group_login_sync'


def sync_tpa_budget_group(backend, user, **kwargs):
    """
    Pipeline entry point: sync the logging-in learner's EnterpriseGroup membership to the
    Learner Credit budget group mapped to the org they logged in under.

    Args:
        backend: The class handling the SSO interaction (SAML, OAuth, etc)
        user: The user object in the process of being logged in with
        **kwargs: Any remaining pipeline variables

    Never raises - a bug here must never be able to block a login for any customer.
    """
    if not waffle.switch_is_active(ENABLE_TPA_ORG_GROUP_LOGIN_SYNC_SWITCH):
        return

    try:
        request = backend.strategy.request
        pipeline = {'backend': backend.name, 'kwargs': kwargs}
        enterprise_customer = get_enterprise_customer_for_running_pipeline(request, pipeline)
        if enterprise_customer is None:
            return

        sync_learner_budget_group(user, enterprise_customer)
    except Exception as e:  # pylint: disable=broad-exception-caught
        log.warning(
            f'[OrgGroupSync] Error resolving enterprise customer for user {getattr(user, "id", None)} '
            f'while syncing budget group: {e}',
            exc_info=True,
        )
